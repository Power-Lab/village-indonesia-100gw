#!/usr/bin/env python3
"""Village solar capacity-factor profiles directly from ERA5 (no geodata).

Pulls ERA5 surface solar radiation (and 2 m temperature) from the Copernicus CDS
and computes hourly PV capacity factors with a transparent, documented model —
then samples the nearest grid cell to each village. Output feeds
village_generators_variability.csv (hourly CF) and gives annual CF / full-load
hours per village.

Two input modes:
  --era5-file <nc>   use an ERA5 NetCDF you already downloaded
  (default)          download via cdsapi for --bbox + --year (needs ~/.cdsapirc)

PV model (intentionally simple and auditable; see docs/solar_resource_era5.md):
  GHI(t)  = ssrd(t) / 3600                      # J/m2 per hour -> W/m2
  Tcell   = T2m + (NOCT-20)/800 * GHI           # cell temperature
  CF(t)   = clip(GHI/1000, 0, 1) * PR * (1 + gamma*(Tcell-25))
where PR (performance ratio), NOCT, gamma are parameters. This is a GHI-based
fixed-array estimate; it captures irradiance + temperature derating without full
plane-of-array transposition. Good for planning CF *shapes*; calibrate annual
energy with --target-flh if a specific yield is required.

Usage
-----
  python tools/solar_resource_era5.py --points villages.csv --year 2023 \
      --bbox 121 -11 125 -8.5 --out-dir solar_ntt
"""
import argparse
import glob
import os
import sys
import zipfile


CDS_DATASET = "reanalysis-era5-single-levels"


def download_era5(bbox, year, out_nc):
    import cdsapi
    w, s, e, n = bbox
    c = cdsapi.Client()
    req = {
        "product_type": "reanalysis",
        "variable": ["surface_solar_radiation_downwards", "2m_temperature"],
        "year": str(year),
        "month": [f"{m:02d}" for m in range(1, 13)],
        "day": [f"{d:02d}" for d in range(1, 32)],
        "time": [f"{h:02d}:00" for h in range(24)],
        "area": [n, w, s, e],  # CDS order: North, West, South, East
        "data_format": "netcdf",
    }
    print(f"  requesting ERA5 {year} for area N{n} W{w} S{s} E{e} (CDS may queue)...")
    c.retrieve(CDS_DATASET, req, out_nc)
    return out_nc


def open_era5(path):
    """Open an ERA5 file, transparently unzipping if CDS delivered a zip."""
    import xarray as xr
    with open(path, "rb") as f:
        magic = f.read(4)
    if magic[:2] == b"PK":  # zip wrapper
        d = path + "_unzipped"
        os.makedirs(d, exist_ok=True)
        try:
            with zipfile.ZipFile(path) as z:
                z.extractall(d)
        except zipfile.BadZipFile:
            sys.exit(f"{path} is a truncated/corrupt zip — re-download it")
        ncs = glob.glob(os.path.join(d, "*.nc"))
        if not ncs:
            sys.exit(f"no .nc inside {path}")
        if len(ncs) > 1:
            return xr.open_mfdataset(ncs, combine="by_coords")
        return xr.open_dataset(ncs[0])
    return xr.open_dataset(path)


def pv_capacity_factor(ds, pr, noct, gamma):
    """Return an xarray DataArray CF(time,lat,lon) in [0,1]."""
    import numpy as np
    # variable names differ across CDS vintages
    ssrd = ds[next(v for v in ("ssrd", "surface_solar_radiation_downwards") if v in ds)]
    ghi = ssrd / 3600.0  # J m-2 per hour -> mean W m-2
    t2m = None
    for v in ("t2m", "2m_temperature"):
        if v in ds:
            t2m = ds[v] - 273.15  # K -> degC
            break
    if t2m is None:
        t2m = ghi * 0.0 + 25.0  # no temp data -> assume STC
    tcell = t2m + (noct - 20.0) / 800.0 * ghi
    cf = (ghi / 1000.0).clip(0, 1) * pr * (1.0 + gamma * (tcell - 25.0))
    return cf.clip(0, 1).rename("cf")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--points", required=True, help="village points CSV (id + lat/lon)")
    ap.add_argument("--year", type=int, default=2023)
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"),
                    default=[121, -11, 125, -8.5])
    ap.add_argument("--era5-file", help="use an existing ERA5 NetCDF instead of downloading")
    ap.add_argument("--out-dir", default="solar_era5")
    ap.add_argument("--pr", type=float, default=0.80, help="performance ratio")
    ap.add_argument("--noct", type=float, default=45.0, help="nominal operating cell temp (degC)")
    ap.add_argument("--gamma", type=float, default=-0.004, help="power temp coefficient (/degC)")
    ap.add_argument("--target-flh", type=float, default=None,
                    help="scale CF so mean annual full-load hours = this (optional calibration)")
    ap.add_argument("--utc-offset", type=int, default=8,
                    help="hours to shift CF from ERA5 UTC to local time so the solar "
                         "peak aligns with local demand (NTT/WITA = +8, WIB = +7, WIT = +9)")
    args = ap.parse_args()

    import numpy as np
    import pandas as pd

    os.makedirs(args.out_dir, exist_ok=True)

    src = args.era5_file
    if not src:
        try:
            import cdsapi  # noqa: F401
        except ImportError:
            sys.exit("cdsapi not installed and no --era5-file given")
        if not os.path.exists(os.path.expanduser("~/.cdsapirc")):
            sys.exit("no ~/.cdsapirc — set up CDS credentials (see docs/solar_resource_era5.md)")
        src = os.path.join(args.out_dir, f"era5_{args.year}.nc")
        if not os.path.exists(src):
            download_era5(args.bbox, args.year, src)

    print(f"1) opening ERA5: {src}")
    ds = open_era5(src)
    latname = next(v for v in ("latitude", "lat") if v in ds.coords)
    lonname = next(v for v in ("longitude", "lon") if v in ds.coords)

    print("2) computing PV capacity factor")
    cf = pv_capacity_factor(ds, args.pr, args.noct, args.gamma)
    if args.utc_offset:
        # ERA5 is UTC; roll along time so the solar peak lands at local noon and
        # aligns with the (local-time) village demand profiles
        tdim = next((d for d in ("valid_time", "time") if d in cf.dims), None)
        if tdim:
            cf = cf.roll({tdim: args.utc_offset}, roll_coords=False)
            print(f"   shifted UTC -> local by +{args.utc_offset} h")
    if args.target_flh:
        cur = float(cf.mean()) * 8760
        cf = (cf * (args.target_flh / cur)).clip(0, 1)
        print(f"   calibrated to {args.target_flh:.0f} FLH (was {cur:.0f})")

    print("3) sampling nearest grid cell per village")
    pts = pd.read_csv(args.points)
    latc = next((c for c in ("lat", "Latitude", "latitude") if c in pts.columns), None)
    lonc = next((c for c in ("lon", "Longitude", "longitude", "lng") if c in pts.columns), None)
    idc = next((c for c in ("id", "village", "name", "Village") if c in pts.columns), None)
    if not (latc and lonc):
        sys.exit("points CSV needs latitude/longitude columns")
    ids = pts[idc].astype(str) if idc else pts.index.astype(str)

    cols, annual = {}, []
    for vid, lat, lon in zip(ids, pts[latc], pts[lonc]):
        ser = cf.sel({latname: lat, lonname: lon}, method="nearest").to_pandas()
        cols[f"village_{vid}"] = np.asarray(ser.values, dtype=float)
        annual.append((vid, float(np.nanmean(ser.values)), float(np.nanmean(ser.values) * 8760)))

    hourly = pd.DataFrame(cols)
    tname = next((t for t in ("valid_time", "time") if t in ds.coords), None)
    if tname:
        hourly.insert(0, "time", pd.to_datetime(ds[tname].values)[: len(hourly)])
    hp = os.path.join(args.out_dir, "village_solar_cf_hourly.csv")
    hourly.to_csv(hp, index=False)
    ann = pd.DataFrame(annual, columns=["village", "mean_cf", "full_load_hours"])
    ap_ = os.path.join(args.out_dir, "village_solar_annual.csv")
    ann.to_csv(ap_, index=False)

    print(f"   wrote {hp}  ({hourly.shape[0]} hours x {len(cols)} villages)")
    print(f"   wrote {ap_}  (mean CF {ann['mean_cf'].mean():.3f}, "
          f"FLH {ann['full_load_hours'].mean():.0f} h)")


if __name__ == "__main__":
    main()
