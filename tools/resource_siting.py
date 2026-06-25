#!/usr/bin/env python3
"""Per-site renewable siting from the QGIS resource-assessment layers.

For each point (industrial park or village), compute:
  - solar_MW    : developable solar capacity on suitable land near the point
  - hubdist_km  : distance to the nearest substation (grid proximity)
  - hub_name    : name of that nearest substation

These map directly onto the model's village inputs:
  - solar_MW   -> village solar Max_Cap_MW (the per-village PV ceiling)
  - hubdist_km -> interconnection feasibility / cost; nearest-substation -> Zone

Solar capacity comes from `candidate_solar_vector.gpkg`, whose polygons already
carry a `solar_MW` attribute (suitable land area x PV power density, ~62 MW/km2,
screened by slope + land cover + GHI in the QGIS project). Two aggregation modes:

  buffer    (default) sum solar_MW of candidate polygons within RADIUS km of the
            point. Land can be shared between nearby points. Physically: "this
            site can develop solar within R km."  Validated to reproduce the
            near-grid industrial-park figures at R=15 km.

  allocate  assign each candidate polygon to its single nearest point (Voronoi),
            then sum per point. Partitions all land with no double-counting;
            gives isolated points a large catchment. Better when points are
            dense and you want a clean partition.

Source layers default to ~/Desktop/QGIS_NEW (override with --gis-dir):
  candidate_solar_vector.gpkg   suitable-land polygons with solar_MW
  substations_projected.shp     substation points (for hubdist)

Usage
-----
  # validate against the existing industrial-park output
  python tools/resource_siting.py --validate

  # run on a village points CSV (needs columns: id, lat/Latitude, lon/Longitude)
  python tools/resource_siting.py --points villages.csv --radius-km 5 --out village_siting.csv
"""
import argparse
import os
import sys
import warnings

warnings.filterwarnings("ignore")

# Web Mercator: matches the original QGIS analysis CRS. Indonesia straddles the
# equator so distance/area distortion is modest; for a final report a per-UTM-zone
# CRS would be marginally more accurate (see --metric-crs).
DEFAULT_CRS = 3857
DEFAULT_GIS_DIR = os.path.expanduser("~/Desktop/QGIS_NEW")
LAT_ALIASES = ("lat", "Latitude", "latitude", "LAT")
LON_ALIASES = ("lon", "Longitude", "longitude", "LON", "lng")


def _load(gis_dir, metric_crs, candidate="candidate_solar_vector.gpkg"):
    import geopandas as gpd
    cand_path = candidate if os.path.isabs(candidate) else os.path.join(gis_dir, candidate)
    cand = gpd.read_file(cand_path)
    if "solar_MW" not in cand.columns:
        sys.exit(f"{os.path.basename(cand_path)} has no 'solar_MW' column")
    cand = cand[cand["solar_MW"].notna() & (cand["solar_MW"] > 0)].to_crs(metric_crs)
    subs = gpd.read_file(os.path.join(gis_dir, "substations_projected.shp")).to_crs(metric_crs)
    return cand.reset_index(drop=True), subs.reset_index(drop=True)


def _sub_name_col(subs):
    for c in ("HubName", "name", "Name", "NAME"):
        if c in subs.columns:
            return c
    return None


def site_capacity(points_gdf, cand, subs, radius_km, mode):
    """points_gdf: GeoDataFrame of Point geometries in the metric CRS.
    Returns a DataFrame with solar_MW, hubdist_km, hub_name per point (by index)."""
    import pandas as pd

    cand_sidx = cand.sindex
    sub_sidx = subs.sindex
    name_col = _sub_name_col(subs)

    # --- solar capacity ---
    if mode == "buffer":
        R = radius_km * 1000.0
        cand_area = cand.geometry.area.values  # full polygon areas (metric CRS)
        solar = []
        for geom in points_gdf.geometry:
            buf = geom.buffer(R)
            idx = list(cand_sidx.query(buf, predicate="intersects"))
            if not idx:
                solar.append(0.0); continue
            sub = cand.iloc[idx]
            # area-clip: count only the suitable land that falls INSIDE the buffer,
            # weighting each polygon's solar_MW by its in-buffer area fraction.
            # (Summing whole polygons over-counts when candidate polygons are large.)
            inside = sub.geometry.intersection(buf).area.values
            frac = inside / cand_area[idx]
            solar.append(float((sub["solar_MW"].values * frac).sum()))
    elif mode == "allocate":
        # assign each candidate polygon (by centroid) to the nearest point
        cent = cand.geometry.centroid
        pt_sidx = points_gdf.sindex
        owner = [list(pt_sidx.nearest(c))[1][0] for c in cent]
        agg = cand.assign(_own=owner).groupby("_own")["solar_MW"].sum()
        solar = [agg.get(i, 0.0) for i in range(len(points_gdf))]
    else:
        sys.exit(f"unknown mode: {mode}")

    # --- grid proximity (nearest substation) ---
    hubdist, hubname = [], []
    for geom in points_gdf.geometry:
        j = list(sub_sidx.nearest(geom))[1][0]
        hubdist.append(geom.distance(subs.geometry.iloc[j]) / 1000.0)
        hubname.append(str(subs.iloc[j][name_col]) if name_col else f"sub_{j}")

    return pd.DataFrame(
        {"solar_MW": solar, "hubdist_km": hubdist, "hub_name": hubname},
        index=points_gdf.index,
    )


def _detect_latlon(columns):
    lat = next((c for c in LAT_ALIASES if c in columns), None)
    lon = next((c for c in LON_ALIASES if c in columns), None)
    return lat, lon


def village_solar_capacity(points_df, gis_dir=DEFAULT_GIS_DIR,
                           candidate="candidate_solar_vector.gpkg",
                           radius_km=5.0, mode="buffer", metric_crs=DEFAULT_CRS,
                           lat_col=None, lon_col=None):
    """Library entry point used by the NTT model build.

    Given a pandas DataFrame of points carrying latitude/longitude columns,
    return a DataFrame (aligned to points_df.index) with columns
    ``solar_MW``, ``hubdist_km`` and ``hub_name``. Rows whose coordinates are
    missing/non-finite are returned with NaN (the caller decides the fallback);
    they are never silently dropped, so the result lines up row-for-row with the
    input village list.
    """
    import geopandas as gpd
    import numpy as np
    import pandas as pd

    lat = lat_col or _detect_latlon(points_df.columns)[0]
    lon = lon_col or _detect_latlon(points_df.columns)[1]
    if not lat or not lon:
        raise ValueError("points need latitude/longitude columns "
                         f"(one of {LAT_ALIASES} / {LON_ALIASES})")

    cand, subs = _load(gis_dir, metric_crs, candidate)

    out = pd.DataFrame(
        {"solar_MW": np.nan, "hubdist_km": np.nan, "hub_name": None},
        index=points_df.index,
    )
    valid = points_df[lat].notna() & points_df[lon].notna()
    if valid.any():
        sub = points_df.loc[valid]
        g = gpd.GeoDataFrame(
            sub, geometry=gpd.points_from_xy(sub[lon], sub[lat]), crs=4326
        ).to_crs(metric_crs)
        res = site_capacity(g, cand, subs, radius_km, mode)
        out.loc[valid, ["solar_MW", "hubdist_km", "hub_name"]] = res.values
    return out


def _points_from_csv(path, metric_crs):
    import geopandas as gpd
    import pandas as pd

    df = pd.read_csv(path)
    lat, lon = _detect_latlon(df.columns)
    if not lat or not lon:
        sys.exit("points CSV needs latitude/longitude columns (lat/Latitude, lon/Longitude)")
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lon], df[lat]), crs=4326)
    return g.to_crs(metric_crs)


def cmd_run(args):
    import pandas as pd
    cand, subs = _load(args.gis_dir, args.metric_crs, args.candidate)
    pts = _points_from_csv(args.points, args.metric_crs)
    res = site_capacity(pts, cand, subs, args.radius_km, args.mode)
    out = pd.concat([pts.drop(columns="geometry").reset_index(drop=True),
                     res.reset_index(drop=True)], axis=1)
    out["solar_MW"] = out["solar_MW"].round(1)
    out["hubdist_km"] = out["hubdist_km"].round(3)
    out.to_csv(args.out, index=False)
    print(f"wrote {args.out}: {len(out)} points "
          f"(mode={args.mode}, radius={args.radius_km} km)")
    print(f"  solar_MW   total={out['solar_MW'].sum():.0f}  "
          f"median={out['solar_MW'].median():.1f}")
    print(f"  hubdist_km median={out['hubdist_km'].median():.2f}  "
          f"max={out['hubdist_km'].max():.2f}")


def cmd_validate(args):
    """Reproduce the industrial-park output to confirm the method + CRS."""
    import geopandas as gpd
    import numpy as np
    import pandas as pd

    cand, subs = _load(args.gis_dir, args.metric_crs, args.candidate)
    parks = gpd.read_file(os.path.join(args.gis_dir, "parks_projected_new.gpkg")).to_crs(args.metric_crs)
    parks = parks.reset_index(drop=True)
    known = pd.read_csv(os.path.join(args.gis_dir, "solar_capacity_by_industrial_parks.csv"))
    kmw = dict(zip(known["Plant name"].str.replace(" power station", "", regex=False).str.strip(),
                   known["solar_MW_sum"]))
    khub = dict(zip(known["Plant name"].str.replace(" power station", "", regex=False).str.strip(),
                    known["HubDist"]))
    res = site_capacity(parks, cand, subs, args.radius_km, args.mode)
    rows = []
    for i, p in parks.iterrows():
        nm = str(p["Power Plant"]).replace(" power station", "").strip()
        key = [k for k in kmw if k and (k in nm or nm in k) and not np.isnan(kmw[k])]
        if not key:
            continue
        k = key[0]
        rows.append((nm[:30], kmw[k], round(res.loc[i, "solar_MW"]),
                     round(khub[k], 2), round(res.loc[i, "hubdist_km"], 2)))
    df = pd.DataFrame(rows, columns=["site", "known_MW", "calc_MW", "known_hub", "calc_hub"])
    df["MW_ok"] = (df["calc_MW"] - df["known_MW"]).abs() <= df["known_MW"] * 0.03 + 1
    print(df.to_string(index=False))
    hubcorr = df["known_hub"].corr(df["calc_hub"])
    print(f"\nmode={args.mode} radius={args.radius_km}km | "
          f"solar exact(±3%): {df['MW_ok'].sum()}/{len(df)} | "
          f"hubdist corr: {hubcorr:.3f} | "
          f"hubdist medianΔ: {(df['calc_hub']-df['known_hub']).abs().median():.2f} km")
    print("Note: near-grid parks reproduce exactly; remote/co-located parks differ "
          "(original park run mixed buffer + nearest-allocation). For villages a "
          "single consistent mode + radius is the right, reproducible choice.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gis-dir", default=os.path.expanduser("~/Desktop/QGIS_NEW"),
                    help="folder with candidate_solar_vector.gpkg, substations_projected.shp")
    ap.add_argument("--candidate", default="candidate_solar_vector.gpkg",
                    help="candidate-solar layer: filename in --gis-dir, or an absolute path. "
                         "Use candidate_solar_timor.gpkg for the NTT/Timor case-study region "
                         "(the default layer is clipped at lat -9.0 and excludes Timor).")
    ap.add_argument("--radius-km", type=float, default=15.0,
                    help="buffer radius for solar capacity (villages: try 2-10 km)")
    ap.add_argument("--mode", choices=["buffer", "allocate"], default="buffer")
    ap.add_argument("--metric-crs", type=int, default=DEFAULT_CRS,
                    help="projected EPSG for distance/area (default 3857, matches the QGIS analysis)")
    ap.add_argument("--points", help="CSV of points to site (id + lat/lon columns)")
    ap.add_argument("--out", default="resource_siting.csv")
    ap.add_argument("--validate", action="store_true",
                    help="reproduce the industrial-park output instead of running --points")
    args = ap.parse_args()

    if args.validate:
        cmd_validate(args)
    elif args.points:
        cmd_run(args)
    else:
        ap.error("provide --points <csv> or --validate")


if __name__ == "__main__":
    main()
