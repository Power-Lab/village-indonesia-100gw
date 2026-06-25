#!/usr/bin/env python3
"""Download Copernicus GLO-30 DEM tiles for a bbox and compute a slope raster.

Fills the land-suitability gap for NTT/Timor: the original QGIS slope layer
(`idn_slope.tif`) stops at latitude -9.0, excluding the Timor/Sabu/Rote
case-study region. This pulls the public Copernicus 30 m DEM (no credentials)
for any bbox, mosaics it, reprojects to a metric CRS, and derives slope (degrees)
plus an optional slope-suitability mask — the missing input for rebuilding the
candidate-solar layer south of -9.

Slope is computed with rasterio + numpy (the GDAL `gdaldem` CLI is broken in some
conda environments). Tiles come from the AWS Open Data bucket:
  https://copernicus-dem-30m.s3.amazonaws.com  (1°x1° COG tiles, named by SW corner)

Usage
-----
  # Timor case-study extent
  python tools/dem_slope.py --bbox 121 -11 125 -8.5 --out-dir gis_ntt --max-slope-deg 15

Outputs (in --out-dir):
  dem_mosaic.tif        merged DEM (EPSG:4326)
  slope_deg.tif         slope in degrees (metric CRS)
  slope_suitable.tif    1 where slope <= --max-slope-deg else 0 (if flag given)
"""
import argparse
import math
import os
import sys
import urllib.request

BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"


def tile_name(lat, lon):
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def tiles_for_bbox(w, s, e, n):
    """1x1 deg tiles (by SW corner integer) covering the bbox."""
    out = []
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            out.append((lat, lon))
    return out


def _expected_size(url):
    """Content-Length from a HEAD request (None if the server won't say / 404)."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            cl = r.headers.get("Content-Length")
            return int(cl) if cl else None
    except Exception:
        return None


def _fetch_one(url, dst, retries=3):
    """Download url -> dst atomically, verifying the byte count matches the
    server's Content-Length. Returns True on a complete file.

    Copernicus tiles are large COGs; a stalled connection leaves a truncated
    file that later hangs/breaks rasterio.merge. We download to a .part file,
    check the size, retry, and only then rename into place — so a half-written
    tile is never mistaken for a valid cache.
    """
    expected = _expected_size(url)
    if expected is None:
        return False  # treat as absent (ocean tiles 404 here)
    part = dst + ".part"
    for attempt in range(1, retries + 1):
        try:
            urllib.request.urlretrieve(url, part)
            got = os.path.getsize(part)
            if got == expected:
                os.replace(part, dst)
                return True
            print(f"    truncated ({got:,}/{expected:,} bytes), retry {attempt}/{retries}", flush=True)
        except Exception as ex:
            print(f"    download error ({ex}), retry {attempt}/{retries}", flush=True)
        finally:
            if os.path.exists(part):
                os.remove(part)
    return False


def _cache_ok(dst, url):
    """A cached tile is trusted only if its size matches the server's."""
    if not os.path.exists(dst):
        return False
    expected = _expected_size(url)
    return expected is not None and os.path.getsize(dst) == expected


def download_tiles(bbox, cache):
    os.makedirs(cache, exist_ok=True)
    w, s, e, n = bbox
    paths = []
    for lat, lon in tiles_for_bbox(w, s, e, n):
        nm = tile_name(lat, lon)
        url = f"{BUCKET}/{nm}/{nm}.tif"
        dst = os.path.join(cache, nm + ".tif")
        if _cache_ok(dst, url):
            paths.append(dst); print(f"  cached {nm}"); continue
        if os.path.exists(dst):
            print(f"  re-fetching {nm} (cached copy is truncated) ...", flush=True)
            os.remove(dst)
        else:
            print(f"  downloading {nm} ...", flush=True)
        if _fetch_one(url, dst):
            paths.append(dst)
        else:
            print(f"  (no tile {nm}: absent or unfetchable)")  # ocean tiles legitimately absent
    if not paths:
        sys.exit("no DEM tiles found for that bbox (all ocean?)")
    return paths


def utm_epsg(lon, lat):
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"), required=True)
    ap.add_argument("--out-dir", default="gis_ntt")
    ap.add_argument("--cache-dir", default=None, help="DEM tile cache (default <out-dir>/dem_tiles)")
    ap.add_argument("--max-slope-deg", type=float, default=None,
                    help="if set, also write slope_suitable.tif (1 where slope <= this)")
    args = ap.parse_args()

    import numpy as np
    import rasterio
    from rasterio.merge import merge
    from rasterio.warp import calculate_default_transform, reproject, Resampling

    os.makedirs(args.out_dir, exist_ok=True)
    cache = args.cache_dir or os.path.join(args.out_dir, "dem_tiles")

    print("1) downloading Copernicus DEM tiles")
    tiles = download_tiles(args.bbox, cache)

    print("2) mosaicking")
    srcs = [rasterio.open(t) for t in tiles]
    mosaic, mtransform = merge(srcs)
    meta = srcs[0].meta.copy()
    meta.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=mtransform, count=1)
    dem_path = os.path.join(args.out_dir, "dem_mosaic.tif")
    with rasterio.open(dem_path, "w", **meta) as dst:
        dst.write(mosaic[0], 1)
    for s_ in srcs:
        s_.close()

    print("3) reprojecting to metric UTM and computing slope")
    w, s, e, n = args.bbox
    dst_crs = f"EPSG:{utm_epsg((w + e) / 2, (s + n) / 2)}"
    with rasterio.open(dem_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds)
        dem_m = np.empty((height, width), dtype="float32")
        reproject(source=rasterio.band(src, 1), destination=dem_m,
                  src_transform=src.transform, src_crs=src.crs,
                  dst_transform=transform, dst_crs=dst_crs, resampling=Resampling.bilinear)

    px = abs(transform.a)
    py = abs(transform.e)
    gy, gx = np.gradient(dem_m, py, px)
    slope_deg = np.degrees(np.arctan(np.sqrt(gx ** 2 + gy ** 2))).astype("float32")

    smeta = dict(driver="GTiff", height=height, width=width, count=1,
                 dtype="float32", crs=dst_crs, transform=transform, nodata=-9999)
    slope_path = os.path.join(args.out_dir, "slope_deg.tif")
    with rasterio.open(slope_path, "w", **smeta) as dst:
        dst.write(slope_deg, 1)
    print(f"   wrote {slope_path}  (slope deg: min {np.nanmin(slope_deg):.1f}, "
          f"median {np.nanmedian(slope_deg):.1f}, max {np.nanmax(slope_deg):.1f})")

    if args.max_slope_deg is not None:
        suit = (slope_deg <= args.max_slope_deg).astype("uint8")
        smeta2 = dict(smeta); smeta2.update(dtype="uint8", nodata=255)
        sp = os.path.join(args.out_dir, "slope_suitable.tif")
        with rasterio.open(sp, "w", **smeta2) as dst:
            dst.write(suit, 1)
        frac = suit.mean() * 100
        print(f"   wrote {sp}  ({frac:.0f}% of pixels <= {args.max_slope_deg}deg)")

    print("done.")


if __name__ == "__main__":
    main()
