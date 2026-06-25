#!/usr/bin/env python3
"""Apply the GIS resource assessment to a built Timor village dataset.

This is the bridge that completes the resource-assessment pipeline:

    village coordinates  ->  developable solar land (MW)  ->  model solar cap

For each village it reads the coordinates from the dataset manifest, computes the
developable-solar ceiling near that point from the candidate-land layer (via
``tools.resource_siting``), and writes that value into ``village_generators.csv``
as the solar row's ``Max_Cap_MW``. In this model ``Max_Cap_MW == 0`` means
*unbounded*; a positive value upper-bounds the village's new solar build to the
land it can actually develop (see functions/optimizer.jl, the VIL_ED_NEW loop).

It also writes an audit file ``village_solar_potential.csv`` next to the dataset
so the per-village land ceiling, grid-proximity, and which villages fell back to
the regional median (missing coordinates) are all inspectable.

Run AFTER tools.ntt.build_timor (which writes Max_Cap_MW = 0); or pass the same
options to build_timor's --solar-cap* flags to bake it in at build time.

Usage
-----
  # Belu (uses the Timor candidate layer built by candidate_land.py)
  python -m tools.ntt.solar_potential \
      --dataset data_indonesia/2030/timor_belu \
      --candidate candidate_solar_timor.gpkg \
      --radius-km 5

  python -m tools.ntt.solar_potential --dataset data_indonesia/2030/timor_belu \
      --candidate candidate_solar_timor.gpkg --dry-run     # preview, write nothing
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _fmt(x):
    """Tidy numeric for the CSV: integers without a decimal, else 1 dp."""
    xr = round(float(x), 1)
    return str(int(xr)) if xr == int(xr) else f"{xr:.1f}"


def compute_caps(dataset_dir, manifest, gis_dir, candidate, radius_km, mode, fallback):
    """Return (manifest_df_with_caps, id_col, fill_value, stats). Pure: no writes."""
    import pandas as pd

    sys.path.insert(0, str(REPO))
    from tools.resource_siting import village_solar_capacity

    man = pd.read_csv(dataset_dir / manifest)
    id_col = "Village" if "Village" in man.columns else man.columns[0]

    res = village_solar_capacity(
        man, gis_dir=gis_dir, candidate=candidate, radius_km=radius_km, mode=mode
    )
    man = pd.concat([man, res], axis=1)

    sited = man["solar_MW"].notna()
    if fallback == "median" and sited.any():
        fill = round(float(man.loc[sited, "solar_MW"].median()), 1)
    else:
        fill = 0.0
    man["sited"] = sited
    man["solar_cap_MW"] = man["solar_MW"].fillna(fill).round(1)

    stats = {
        "n": len(man),
        "n_sited": int(sited.sum()),
        "n_fallback": int((~sited).sum()),
        "fill": fill,
        "total_MW": float(man["solar_cap_MW"].sum()),
        "median_MW": float(man.loc[sited, "solar_MW"].median()) if sited.any() else 0.0,
        "min_MW": float(man.loc[sited, "solar_MW"].min()) if sited.any() else 0.0,
        "max_MW": float(man.loc[sited, "solar_MW"].max()) if sited.any() else 0.0,
    }
    return man, id_col, fill, stats


def write_audit(man, id_col, path):
    cols = [id_col, "kabupaten", "kecamatan", "desa", "archetype", "households",
            "lat", "lon", "sited", "solar_MW", "solar_cap_MW", "hubdist_km",
            "hub_name", "peak_mw"]
    cols = [c for c in cols if c in man.columns]
    audit = man[cols].copy()
    if "solar_MW" in audit:
        audit["solar_MW"] = audit["solar_MW"].round(1)
    if "hubdist_km" in audit:
        audit["hubdist_km"] = audit["hubdist_km"].round(3)
    audit.to_csv(path, index=False)


def patch_generators(gen_path, caps_by_id):
    """Surgically set Max_Cap_MW on solar rows only; every other byte preserved.

    Returns (n_patched, n_solar_rows). Uses the csv module (not pandas) so the
    other columns are not reformatted in the file the Julia model reads.
    """
    with open(gen_path, newline="") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    ix_tech = header.index("technology")
    ix_cap = header.index("Max_Cap_MW")
    ix_vil = header.index("Village")
    n_patched = n_solar = 0
    for r in rows[1:]:
        if r[ix_tech] == "solar":
            n_solar += 1
            key = r[ix_vil]
            if key in caps_by_id:
                r[ix_cap] = _fmt(caps_by_id[key])
                n_patched += 1
    with open(gen_path, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    return n_patched, n_solar


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True,
                    help="dataset dir, e.g. data_indonesia/2030/timor_belu")
    ap.add_argument("--manifest", default="timor_villages_manifest.csv")
    ap.add_argument("--generators", default="village_generators.csv")
    ap.add_argument("--gis-dir", default=os.path.expanduser("~/Desktop/QGIS_NEW"))
    ap.add_argument("--candidate", default="candidate_solar_timor.gpkg",
                    help="candidate-solar layer in --gis-dir (or absolute path)")
    ap.add_argument("--radius-km", type=float, default=5.0,
                    help="buffer radius for the per-village land ceiling")
    ap.add_argument("--mode", choices=["buffer", "allocate"], default="buffer")
    ap.add_argument("--fallback", choices=["median", "zero"], default="median",
                    help="ceiling for villages without coordinates: regional median "
                         "(a guardrail) or zero (left unbounded)")
    ap.add_argument("--audit", default="village_solar_potential.csv")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print the summary but write nothing")
    args = ap.parse_args()

    ds = Path(args.dataset)
    if not ds.is_absolute():
        ds = REPO / ds
    if not ds.exists():
        sys.exit(f"dataset dir not found: {ds}")
    gis_dir = os.path.expanduser(args.gis_dir)

    man, id_col, fill, st = compute_caps(
        ds, args.manifest, gis_dir, args.candidate,
        args.radius_km, args.mode, args.fallback)

    print(f"resource assessment for {ds.relative_to(REPO) if ds.is_relative_to(REPO) else ds}")
    print(f"  candidate layer : {args.candidate}  (mode={args.mode}, radius={args.radius_km} km)")
    print(f"  villages        : {st['n']}  sited={st['n_sited']}  "
          f"fallback={st['n_fallback']} (-> {st['fill']} MW, {args.fallback})")
    print(f"  solar ceiling MW: total={st['total_MW']:.0f}  "
          f"min={st['min_MW']:.1f}  median={st['median_MW']:.1f}  max={st['max_MW']:.1f}")

    if args.dry_run:
        print("  (dry-run: no files written)")
        return

    audit_path = ds / args.audit
    write_audit(man, id_col, audit_path)
    print(f"  wrote {audit_path.name}")

    caps = {str(v): c for v, c in zip(man[id_col], man["solar_cap_MW"])}
    n_patched, n_solar = patch_generators(ds / args.generators, caps)
    print(f"  patched {args.generators}: set Max_Cap_MW on {n_patched}/{n_solar} solar rows")


if __name__ == "__main__":
    main()
