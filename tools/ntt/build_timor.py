#!/usr/bin/env python3
"""Build the Timor village-solar dataset for the capacity-expansion model.

Pipeline: source workbooks  ->  Village records (tools.ntt.sources)
          Village + archetype calculator (tools.ntt.calculators)  ->  demand / sizing / costs
          ->  model-ready CSVs in data_indonesia/<year>/<name>/

Every village is one node on a single shared Timor grid bus (Zone 1). Each gets
an existing diesel (Commit=0, capital sunk), a candidate solar PV, and a
candidate battery; whether it connects to the grid is the model's decision
(village_connection.csv gives the per-village interconnection cost).

Usage:
    python -m tools.ntt.build_timor --src-dir <folder-with-3-xlsx> \
        [--kabupaten belu] [--year 2030] [--name timor]
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

from .sources import load_timor_villages, TIMOR_KABUPATEN, norm
from .archetypes import solar_cf_builder
from .calculators import get_calculator
from . import costs as C

REPO = Path(__file__).resolve().parents[2]

# ----------------------------------------------------------------- time setup
REP_PERIODS = 8
HOURS_PER_PERIOD = 168
T = REP_PERIODS * HOURS_PER_PERIOD          # 1344
SUB_WEIGHT = 8760 // REP_PERIODS            # 1095, uniform
CORRESPONDING_WEEKS = [2, 9, 16, 24, 32, 40, 46, 52]
DEMAND_WEEK_FACTOR = [1.00, 0.97, 0.95, 1.02, 1.05, 0.98, 1.00, 1.03]

VOLL = 2000
SEGMENTS = [(1, 1.0, 1.0), (2, 0.9, 0.04), (3, 0.55, 0.024), (4, 0.2, 0.003)]

# Fuel + diesel tech assumptions (match make_timor_demo / isolated-NTT reality)
DIESEL_FUEL = "diesel"
DIESEL_HR = 10.5
DIESEL_VOM = 8.0
DIESEL_COST_MMBTU = 18.0
DIESEL_CO2 = 0.0732

# Interconnection-cost model (documented defaults; tune in verification)
CONNECT_FIXED_IDR = 150_000_000      # Rp: fixed cost to tap the MV grid per village
CONNECT_IDR_PER_KM = 400_000_000     # Rp/km: MV feeder to the grid backbone
CONNECT_DEFAULT_KM = 10.0            # used when a village has no coordinates

# 30-col village generator layout (grid GEN_COLS + a Village column after Zone)
VIL_GEN_COLS = ["R_ID", "Zone", "Village", "Resource", "technology", "owner",
                "Existing_Cap_MW", "Existing_Cap_MWh", "New_Build", "Max_Cap_MW",
                "Inv_Cost_per_MWyr", "Inv_Cost_per_MWhyr",
                "Fixed_OM_Cost_per_MWyr", "Fixed_OM_Cost_per_MWhyr",
                "Var_OM_Cost_per_MWh", "Min_Power_MW",
                "Ramp_Up_Percentage", "Ramp_Dn_Percentage", "Commit",
                "Start_Cost_per_MW", "Start_Fuel_MMBTU_per_MW",
                "Heat_Rate_MMBTU_per_MWh", "Fuel", "Up_Time", "Down_Time",
                "Eff_Up", "Eff_Down", "STOR", "VRE", "RE", "THERM"]
GEN_COLS = [c for c in VIL_GEN_COLS if c != "Village"]


def hod(t):
    return (t - 1) % 24


def week(t):
    return (t - 1) // HOURS_PER_PERIOD


def scalar(rows, i, value):
    return value if i < rows else ""


def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  wrote {path.name} ({len(rows)} rows)")


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def solar_land_caps(villages, gis_dir, candidate, radius_km, mode, fallback="median"):
    """Per-village solar Max_Cap_MW (developable land) from the GIS resource
    assessment, keyed by village id (1..NV). Returns None — leaving every village
    uncapped (Max_Cap_MW = 0) — if geopandas or the candidate layer is missing, so
    a fresh build never hard-fails on the optional GIS dependency.

    Villages without coordinates fall back to the regional median ceiling, the
    same policy as tools.ntt.solar_potential (the standalone retrofit tool)."""
    cand_path = Path(candidate)
    if not cand_path.is_absolute():
        cand_path = Path(gis_dir).expanduser() / candidate
    if not cand_path.exists():
        print(f"  [solar-cap] candidate layer not found: {cand_path}\n"
              f"             leaving solar Max_Cap_MW=0 (uncapped). Build it with "
              f"tools/candidate_land.py first.")
        return None
    try:
        import sys
        sys.path.insert(0, str(REPO))
        import pandas as pd
        from tools.resource_siting import village_solar_capacity
    except Exception as ex:  # geopandas/rasterio not installed
        print(f"  [solar-cap] resource assessment unavailable ({ex}); leaving Max_Cap_MW=0")
        return None

    df = pd.DataFrame({"lat": [v.lat for v in villages], "lon": [v.lon for v in villages]})
    res = village_solar_capacity(df, gis_dir=str(Path(gis_dir).expanduser()),
                                 candidate=str(cand_path), radius_km=radius_km, mode=mode)
    sited = res["solar_MW"].notna()
    fill = (round(float(res.loc[sited, "solar_MW"].median()), 1)
            if (fallback == "median" and sited.any()) else 0.0)
    caps = {}
    for i in range(len(villages)):
        mw = res["solar_MW"].iloc[i]
        caps[i + 1] = round(float(mw), 1) if pd.notna(mw) else fill
    n_fallback = int((~sited).sum())
    print(f"  [solar-cap] sited {int(sited.sum())}/{len(villages)} villages "
          f"(buffer {radius_km} km); {n_fallback} -> median {fill} MW")
    return caps


# ------------------------------------------------------------------ generators
def diesel_row(rid, vid, name, cap):
    """Existing village diesel, Commit=0 (LP), capital sunk, high fuel cost."""
    return [rid, 1, vid, name, "diesel", "village_coop", round(cap, 4), 0, 0, 0,
            0, 0, 18000, 0, DIESEL_VOM, 0, 1.0, 1.0, 0,
            0, 0, DIESEL_HR, DIESEL_FUEL, 0, 0, 1, 1, 0, 0, 0, 1]


def solar_row(rid, vid, name, inv, fom):
    return [rid, 1, vid, name, "solar", "village_coop", 0.0, 0, 1, 0,
            inv, 0, fom, 0, 0, 0, 1, 1, 0,
            0, 0, 0, "None", 0, 0, 1, 1, 0, 1, 1, 0]


def battery_row(rid, vid, name, inv_mw, inv_mwh, fom):
    return [rid, 1, vid, name, "battery", "village_coop", 0, 0, 1, 0,
            inv_mw, inv_mwh, fom, 2000, 1, 0, 1, 1, 0,
            0, 0, 0, "None", 0, 0, 0.92, 0.92, 1, 0, 0, 0]


def build(villages, out_dir, year, solar_cap=False, gis_dir="~/Desktop/QGIS_NEW",
          candidate="candidate_solar_timor.gpkg", solar_radius_km=5.0, solar_mode="buffer"):
    out_dir.mkdir(parents=True, exist_ok=True)
    NV = len(villages)

    # --- per-village demand, sizing, cost via the archetype calculator ------
    demands, costs, diesels, ghis = [], [], [], []
    for v in villages:
        calc = get_calculator(v.archetype)
        d = calc.demand(v)
        cst = calc.costs(calc.sizing(v, d))
        demands.append(d)
        costs.append(cst)
        diesels.append(round(max(d.peak_mw * 1.1, 0.01), 4))
        ghis.append(v.ghi)

    # --- village_generators.csv (diesel + solar + battery per village) ------
    gen_rows, gen_techs = [], []
    rid = 1
    for vid, (v, cst, diesel_mw) in enumerate(zip(villages, costs, diesels), start=1):
        tag = f"{v.kabupaten[:3].lower()}{vid}"
        gen_rows.append(diesel_row(rid, vid, f"pltd_{tag}", diesel_mw)); gen_techs.append("diesel"); rid += 1
        gen_rows.append(solar_row(rid, vid, f"plts_{tag}",
                                  cst.solar_inv_per_mwyr, cst.solar_fom_per_mwyr)); gen_techs.append("solar"); rid += 1
        gen_rows.append(battery_row(rid, vid, f"batt_{tag}",
                                    cst.battery_inv_per_mwyr, cst.battery_inv_per_mwhyr,
                                    cst.battery_fom_per_mwyr)); gen_techs.append("battery"); rid += 1
    # optional: cap each village's solar by developable land (GIS resource assessment)
    if solar_cap:
        caps = solar_land_caps(villages, gis_dir, candidate, solar_radius_km, solar_mode)
        if caps:
            for row in gen_rows:
                if row[4] == "solar":          # row[2]=village id, row[9]=Max_Cap_MW
                    row[9] = caps.get(row[2], 0)
    write_csv(out_dir / "village_generators.csv", VIL_GEN_COLS, gen_rows)

    # --- village_demand.csv (scalar block + hourly per village) -------------
    rows = []
    for t in range(1, T + 1):
        i = t - 1
        row = [scalar(1, i, VOLL),
               scalar(len(SEGMENTS), i, SEGMENTS[i][0] if i < len(SEGMENTS) else ""),
               scalar(len(SEGMENTS), i, SEGMENTS[i][1] if i < len(SEGMENTS) else ""),
               scalar(len(SEGMENTS), i, SEGMENTS[i][2] if i < len(SEGMENTS) else ""),
               t, hod(t)]
        for d in demands:
            row.append(round(d.peak_mw * d.demand_shape[hod(t)] * DEMAND_WEEK_FACTOR[week(t)], 6))
        rows.append(row)
    write_csv(out_dir / "village_demand.csv",
              ["Voll", "Demand_Segment", "Cost_of_Demand_Curtailment_per_MW",
               "Max_Demand_Curtailment", "r_id", "hour"]
              + [f"demand_village{i}" for i in range(1, NV + 1)], rows)

    # --- village_demandheat.csv (zeros — electricity-only) ------------------
    write_csv(out_dir / "village_demandheat.csv",
              ["r_id"] + [f"demand_village{i}" for i in range(1, NV + 1)],
              [[t] + [0] * NV for t in range(1, T + 1)])

    # --- village_generators_variability.csv (GHI-scaled solar) --------------
    cfs = {}
    rows = []
    for t in range(1, T + 1):
        row = [t]
        gi = 0
        for v in villages:
            # diesel, solar, battery per village (solar is the middle one)
            cf = cfs.setdefault(round(v.ghi, 4), solar_cf_builder(v.ghi))
            row += [1.0, cf(t), 1.0]
            gi += 3
        rows.append(row)
    write_csv(out_dir / "village_generators_variability.csv",
              ["r_id"] + [r[3] for r in gen_rows], rows)

    # --- village_connection.csv (per-village interconnection cost) ----------
    # centroid for distance fallback / coordinate-free villages
    coords = [(v.lat, v.lon) for v in villages if v.lat is not None]
    clat = sum(c[0] for c in coords) / len(coords) if coords else -9.7
    clon = sum(c[1] for c in coords) / len(coords) if coords else 124.3
    conn_rows = []
    for vid, (v, d) in enumerate(zip(villages, demands), start=1):
        if v.lat is not None:
            dist = max(1.0, haversine_km(v.lat, v.lon, clat, clon))
        else:
            dist = CONNECT_DEFAULT_KM
        capex_idr = CONNECT_FIXED_IDR + dist * CONNECT_IDR_PER_KM
        cost_per_yr = round(C.idr_to_usd(capex_idr) * C.crf(C.DISCOUNT_RATE, C.LIFETIME_YEARS["grid"]))
        max_connect = round(max(d.peak_mw * 1.5, 0.02), 4)
        conn_rows.append([vid, cost_per_yr, max_connect])
    write_csv(out_dir / "village_connection.csv",
              ["Village", "Cost_per_yr", "Max_Connect_MW"], conn_rows)

    # --- minimal shared grid backstop (Zone 1) ------------------------------
    # one existing PLN diesel so the bus can supply/absorb; zero separate grid demand.
    grid_peak = round(sum(d.peak_mw for d in demands), 3)
    grid_gen_rows = [
        [1, 1, "pln_timor_diesel", "diesel", "pln", round(grid_peak, 3), 0, 0, 0,
         0, 0, 15000, 0, DIESEL_VOM, 0, 1.0, 1.0, 0, 0, 0, DIESEL_HR, DIESEL_FUEL,
         0, 0, 1, 1, 0, 0, 0, 1],
    ]
    write_csv(out_dir / "generators.csv", GEN_COLS, grid_gen_rows)

    rows = []
    for t in range(1, T + 1):
        i = t - 1
        rows.append([scalar(1, i, VOLL),
                     scalar(len(SEGMENTS), i, SEGMENTS[i][0] if i < len(SEGMENTS) else ""),
                     scalar(len(SEGMENTS), i, SEGMENTS[i][1] if i < len(SEGMENTS) else ""),
                     scalar(len(SEGMENTS), i, SEGMENTS[i][2] if i < len(SEGMENTS) else ""),
                     scalar(1, i, REP_PERIODS), scalar(1, i, HOURS_PER_PERIOD),
                     scalar(REP_PERIODS, i, SUB_WEIGHT),
                     scalar(REP_PERIODS, i, CORRESPONDING_WEEKS[i] if i < REP_PERIODS else ""),
                     t, hod(t), 0])
    write_csv(out_dir / "demand.csv",
              ["Voll", "Demand_Segment", "Cost_of_Demand_Curtailment_per_MW",
               "Max_Demand_Curtailment", "Rep_Periods", "Timesteps_per_Rep_Period",
               "Sub_Weights", "corresponding_week", "r_id", "hour", "demand_z1"], rows)

    write_csv(out_dir / "generators_variability.csv",
              ["r_id", "pln_timor_diesel"], [[t, 1.0] for t in range(1, T + 1)])

    write_csv(out_dir / "fuels_data.csv",
              ["Fuel", "Cost_per_MMBtu", "CO2_content_tons_per_MMBtu", "fuel_indices"],
              [["None", 0, 0, 1], [DIESEL_FUEL, DIESEL_COST_MMBTU, DIESEL_CO2, 2]])

    # single-zone network: one self-corridor with zero capacity (placeholder so
    # the grid-family loader finds the file; villages share Zone 1 directly).
    write_csv(out_dir / "network.csv",
              ["r_id", "path_name", "substation_path", "z1", "voltage_kV",
               "distance_km", "B", "Line_Max_Flow_MW", "Line_Max_Reinforcement_MW",
               "Line_Reinforcement_Cost_per_MWyr"],
              [[1, "timor_internal", "timor_bus", 0, 70, 1, 100, 0, 0, 1]])

    # --- manifest -----------------------------------------------------------
    man = [["Village", "kabupaten", "kecamatan", "desa", "archetype", "households",
            "ghi", "ghi_matched", "lat", "lon", "annual_kwh", "peak_mw", "diesel_mw"]]
    for vid, (v, d, diesel_mw) in enumerate(zip(villages, demands, diesels), start=1):
        man.append([vid, v.kabupaten, v.kecamatan, v.desa, v.archetype, v.households,
                    v.ghi, v.matched_ghi, v.lat, v.lon, round(d.annual_kwh),
                    round(d.peak_mw, 5), diesel_mw])
    write_csv(out_dir / "timor_villages_manifest.csv", man[0], man[1:])

    return NV, grid_peak


def main():
    ap = argparse.ArgumentParser(description="Build the Timor village-solar dataset.")
    ap.add_argument("--src-dir", required=True, help="folder containing the 3 source .xlsx")
    ap.add_argument("--kabupaten", default=None,
                    help="restrict to one kabupaten (e.g. belu); default = all four")
    ap.add_argument("--year", default="2030")
    ap.add_argument("--name", default="timor", help="output folder name under data_indonesia/<year>/")
    ap.add_argument("--solar-cap", action="store_true",
                    help="set each village's solar Max_Cap_MW from the GIS land resource "
                         "assessment (needs geopandas + a candidate-solar layer); without "
                         "it solar stays uncapped (Max_Cap_MW=0)")
    ap.add_argument("--gis-dir", default="~/Desktop/QGIS_NEW")
    ap.add_argument("--candidate", default="candidate_solar_timor.gpkg",
                    help="candidate-solar layer in --gis-dir (or absolute path)")
    ap.add_argument("--solar-radius-km", type=float, default=5.0)
    ap.add_argument("--solar-mode", default="buffer", choices=["buffer", "allocate"])
    args = ap.parse_args()

    src = Path(args.src_dir)
    potensi = src / "Data potensi desa.xlsx"
    ghi = src / "NTT_Data_Desa.xlsx"
    kab = {norm(args.kabupaten)} if args.kabupaten else TIMOR_KABUPATEN
    name = f"{args.name}_{args.kabupaten.lower()}" if args.kabupaten else args.name

    print(f"Reading workbooks from {src} ...")
    villages, stats = load_timor_villages(str(potensi), str(ghi), kab)
    print(f"  villages: {stats['villages']}  GHI matched: {stats['ghi_matched']}  "
          f"fell back: {stats['ghi_fell_back']}")

    out_dir = REPO / "data_indonesia" / args.year / name
    print(f"Writing dataset to {out_dir.relative_to(REPO)} ...")
    nv, grid_peak = build(villages, out_dir, args.year, solar_cap=args.solar_cap,
                          gis_dir=args.gis_dir, candidate=args.candidate,
                          solar_radius_km=args.solar_radius_km, solar_mode=args.solar_mode)
    total_gwh = sum(get_calculator(v.archetype).demand(v).annual_kwh for v in villages) / 1e6
    print(f"\nDone: {nv} villages, total demand {total_gwh:,.1f} GWh/yr, "
          f"aggregate peak {grid_peak:.1f} MW.")
    print(f"Run with scenario 'gridvillage', island '{name}', year {args.year}.")


if __name__ == "__main__":
    main()
