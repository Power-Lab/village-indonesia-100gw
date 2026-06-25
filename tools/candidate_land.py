#!/usr/bin/env python3
"""Build a candidate-solar layer (suitable land + capacity) for a region.

Reproduces, in code, the manual QGIS step that produced
`candidate_solar_vector.gpkg` — but for any bounding box, so it can be extended
to the NTT/Timor case-study region (which the original layer omits, being clipped
at lat -9.0). Output is a polygon layer with the same schema the downstream tool
expects: `DN`, `area_m2`, `solar_MW`.

Method (raster overlay on the slope grid, which is already metric):
  candidate = (land cover suitable score >= --min-suitable)
              AND (slope <= --max-slope-deg)
  solar_MW  = polygon area (m2) * --pv-density (MW/km2)

Inputs:
  --landcover   idn_land_cover.shp  (must carry a `suitable` score: 0/2/3)
  --slope       slope_deg.tif from tools/dem_slope.py (metric CRS)

Usage
-----
  # 1) slope for the region
  python tools/dem_slope.py --bbox 123.4 -10.5 125.2 -9 --out-dir gis_timor
  # 2) candidate-solar layer
  python tools/candidate_land.py \
      --landcover ~/Desktop/QGIS_NEW/idn_land_cover.shp \
      --slope gis_timor/slope_deg.tif \
      --bbox 123.4 -10.5 125.2 -9 \
      --out gis_timor/candidate_solar_timor.gpkg
"""
import argparse
import os
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--landcover", required=True, help="land-cover shapefile with a `suitable` score column")
    ap.add_argument("--slope", required=True, help="slope_deg.tif (metric CRS, from dem_slope.py)")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"), required=True)
    ap.add_argument("--out", default="candidate_solar.gpkg")
    ap.add_argument("--min-suitable", type=int, default=2,
                    help="minimum land-cover suitability score to include (2=incl. shrub/savannah, 3=only settlement/farm/bare)")
    ap.add_argument("--max-slope-deg", type=float, default=15.0)
    ap.add_argument("--pv-density", type=float, default=62.0, help="MW per km2 of suitable land")
    ap.add_argument("--suitable-col", default="suitable")
    args = ap.parse_args()

    import geopandas as gpd
    import numpy as np
    import rasterio
    from rasterio.features import rasterize, shapes
    from shapely.geometry import shape
    import warnings
    warnings.filterwarnings("ignore")

    w, s, e, n = args.bbox

    print("1) loading slope grid (defines CRS + resolution)")
    with rasterio.open(args.slope) as ds:
        slope = ds.read(1)
        transform = ds.transform
        crs = ds.crs
        shape_hw = slope.shape
    slope_ok = (slope <= args.max_slope_deg) & np.isfinite(slope)

    print(f"2) loading land cover, filtering suitable >= {args.min_suitable}, clipping to bbox")
    lc = gpd.read_file(args.landcover, bbox=(w, s, e, n))
    if args.suitable_col not in lc.columns:
        sys.exit(f"land cover has no '{args.suitable_col}' column; got {list(lc.columns)}")
    lc = lc[lc[args.suitable_col] >= args.min_suitable]
    if lc.empty:
        sys.exit("no suitable land-cover polygons in bbox")
    lc = lc.to_crs(crs)

    print("3) rasterizing suitable land cover onto the slope grid")
    lc_mask = rasterize(((geom, 1) for geom in lc.geometry),
                        out_shape=shape_hw, transform=transform,
                        fill=0, dtype="uint8", all_touched=False).astype(bool)

    candidate = (lc_mask & slope_ok).astype("uint8")
    npix = int(candidate.sum())
    px_area = abs(transform.a) * abs(transform.e)  # m2 per pixel
    print(f"   candidate pixels: {npix:,}  (~{npix*px_area/1e6:.0f} km2 of suitable land)")

    print("4) polygonizing and attributing solar_MW")
    density_per_m2 = args.pv_density / 1e6
    feats = []
    for geom, val in shapes(candidate, mask=candidate.astype(bool), transform=transform):
        poly = shape(geom)
        a = poly.area  # m2 (metric CRS)
        feats.append({"geometry": poly, "DN": 1, "area_m2": a,
                      "solar_MW": round(a * density_per_m2, 3)})
    out = gpd.GeoDataFrame(feats, crs=crs)
    # Overwrite cleanly: a GeoPackage holds multiple layers, so writing over an
    # existing .gpkg would ADD a layer (leaving a stale first layer that readers
    # pick up by default). Remove any existing file so the result is single-layer.
    if os.path.exists(args.out):
        os.remove(args.out)
    out.to_file(args.out, driver="GPKG")

    print(f"   wrote {args.out}: {len(out)} polygons, "
          f"{out['solar_MW'].sum()/1000:.2f} GW total developable solar")
    print(f"   (min-suitable={args.min_suitable}, max-slope={args.max_slope_deg}deg, "
          f"density={args.pv_density} MW/km2)")


if __name__ == "__main__":
    main()
