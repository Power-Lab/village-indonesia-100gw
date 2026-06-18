#!/usr/bin/env python3
"""Village solar capacity-factor profiles from reanalysis, via GeodataTools/geodata.

Produces the *temporal* solar resource the model needs — hourly PV capacity
factors per village — which the renewable-siting layer (tools/resource_siting.py)
does not provide. Output feeds two things:

  1. village_generators_variability.csv  (hourly CF, one column per village)
  2. annual mean CF / full-load hours per village (spatial quality weighting)

Pipeline (geodata): Dataset (download ERA5/MERRA-2) -> Cutout (subset to the
NTT bbox + year) -> convert.pv (tilted-irradiance PV model) -> sample the nearest
grid cell to each village point.

REQUIRES CREDENTIALS + NETWORK (data is downloaded, not bundled):
  - ERA5  (default): a Copernicus CDS account and ~/.cdsapirc  (cdsapi)
  - MERRA-2          : a NASA Earthdata account (~/.netrc)
See docs/solar_resource_geodata.md for setup. This script is written to be run by
the analyst with those credentials; it is not executed in CI.

Usage
-----
  python tools/solar_resource_geodata.py \
      --points villages.csv --year 2023 \
      --bbox 121 -11 125 -8.5 --panel CSi \
      --out-dir solar_ntt
"""
import argparse
import os
import sys


def build_cutout(module, cfg, name, bbox, year, cutout_dir):
    import geodata
    w, s, e, n = bbox
    # 1) Dataset: ensure raw reanalysis is downloaded for the bbox/period
    ds = geodata.Dataset(
        module=module,
        weather_data_config=cfg,
        years=slice(year, year),
        months=slice(1, 12),
        xs=slice(w, e),
        ys=slice(s, n),
    )
    if not getattr(ds, "prepared", False):
        print(f"  downloading {module} {cfg} for {year} (this can take a while)...")
        ds.get_data()

    # 2) Cutout: the region/time subset geodata converts from
    cutout = geodata.Cutout(
        name=name,
        module=module,
        weather_data_config=cfg,
        xs=slice(w, e),
        ys=slice(s, n),
        years=slice(year, year),
        months=slice(1, 12),
        cutout_dir=cutout_dir,
    )
    cutout.prepare()
    return cutout


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--points", required=True, help="village points CSV (id + lat/lon)")
    ap.add_argument("--year", type=int, default=2023)
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"),
                    default=[121, -11, 125, -8.5], help="NTT/Timor default")
    ap.add_argument("--module", choices=["era5", "merra2"], default="era5")
    ap.add_argument("--panel", default="CSi", help="bundled panel: CSi, CdTe, KANEKA")
    ap.add_argument("--tilt", type=float, default=None,
                    help="panel tilt deg (default = |latitude| of bbox centre)")
    ap.add_argument("--azimuth", type=float, default=0.0,
                    help="panel azimuth deg (0 = equator-facing/North in S hemisphere)")
    ap.add_argument("--out-dir", default="solar_geodata")
    ap.add_argument("--cutout-dir", default=None)
    args = ap.parse_args()

    try:
        import geodata  # noqa: F401
    except ImportError:
        sys.exit("geodata not installed: pip install geodata  (GeodataTools/geodata)")
    import numpy as np
    import pandas as pd

    os.makedirs(args.out_dir, exist_ok=True)
    cfg = "wind_solar_hourly" if args.module == "era5" else "slv_radiation_hourly"
    w, s, e, n = args.bbox
    tilt = args.tilt if args.tilt is not None else abs((s + n) / 2)
    cutout_dir = args.cutout_dir or os.path.join(args.out_dir, "cutouts")

    pts = pd.read_csv(args.points)
    latc = next((c for c in ("lat", "Latitude", "latitude") if c in pts.columns), None)
    lonc = next((c for c in ("lon", "Longitude", "longitude", "lng") if c in pts.columns), None)
    idc = next((c for c in ("id", "village", "name", "Village") if c in pts.columns), None)
    if not (latc and lonc):
        sys.exit("points CSV needs latitude/longitude columns")
    ids = pts[idc].astype(str) if idc else pts.index.astype(str)

    print(f"1) building {args.module} cutout for bbox {args.bbox} year {args.year}")
    cutout = build_cutout(args.module, cfg, f"ntt-solar-{args.year}",
                          args.bbox, args.year, cutout_dir)

    print(f"2) PV conversion (panel={args.panel}, tilt={tilt:.0f}deg, azimuth={args.azimuth:.0f})")
    import geodata
    # capacity factor per grid cell, hourly. orientation: equator-facing fixed tilt.
    cf = geodata.convert.pv(
        cutout,
        panel=args.panel,
        orientation={"slope": float(tilt), "azimuth": float(args.azimuth)},
    )
    # cf is an xarray DataArray (time, y, x) of capacity factor in [0,1]

    print("3) sampling nearest grid cell per village")
    cols = {}
    annual = []
    for vid, lat, lon in zip(ids, pts[latc], pts[lonc]):
        series = cf.sel(y=lat, x=lon, method="nearest").to_pandas()
        cols[f"village_{vid}"] = series.values
        annual.append((vid, float(series.mean()), float(series.mean() * 8760)))
    time_index = cf.indexes.get("time")

    hourly = pd.DataFrame(cols)
    if time_index is not None:
        hourly.insert(0, "time", time_index[: len(hourly)])
    hourly_path = os.path.join(args.out_dir, "village_solar_cf_hourly.csv")
    hourly.to_csv(hourly_path, index=False)

    ann = pd.DataFrame(annual, columns=["village", "mean_cf", "full_load_hours"])
    ann_path = os.path.join(args.out_dir, "village_solar_annual.csv")
    ann.to_csv(ann_path, index=False)

    print(f"   wrote {hourly_path}  ({hourly.shape[0]} hours x {len(cols)} villages)")
    print(f"   wrote {ann_path}  (mean CF {ann['mean_cf'].mean():.3f}, "
          f"FLH {ann['full_load_hours'].mean():.0f} h)")
    print("\nNext: reduce the hourly CF to the model's representative periods and "
          "write it into village_generators_variability.csv (see "
          "docs/solar_resource_geodata.md).")


if __name__ == "__main__":
    main()
