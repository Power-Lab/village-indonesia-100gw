# Resource Siting (solar potential + grid proximity)

`tools/resource_siting.py` turns the QGIS resource-assessment layers into
per-site model inputs. For each point (industrial park or village) it computes:

- **`solar_MW`** — developable solar capacity on suitable land near the point,
  from `candidate_solar_vector.gpkg` (polygons carrying a `solar_MW` attribute =
  suitable land area × PV power density ≈ 62 MW/km², pre-screened by slope, land
  cover, and GHI in the QGIS project).
- **`hubdist_km`** + **`hub_name`** — distance to, and name of, the nearest
  substation (`substations_projected.shp`).

These map onto the model: `solar_MW` → village solar `Max_Cap_MW`; `hubdist_km`
→ interconnection feasibility/cost; nearest substation → grid `Zone`.

## End-to-end pipeline (NTT/Timor) — implemented

Receiving village coordinates and producing the per-village solar land ceiling is
a three-step chain. Steps 1–2 are GIS (need geopandas/rasterio + the QGIS layers);
step 3 is the Julia model.

```bash
# 1) Build the Timor candidate-solar land layer (the default QGIS layer is clipped
#    at lat -9.0 and excludes Timor). Slope first (downloads Copernicus GLO-30 DEM),
#    then land-cover x slope -> candidate_solar_timor.gpkg.
python tools/dem_slope.py --bbox 123.2 -10.5 125.3 -8.9 \
    --out-dir ~/Desktop/QGIS_NEW/gis_timor --max-slope-deg 15
python tools/candidate_land.py \
    --landcover ~/Desktop/QGIS_NEW/idn_land_cover.shp \
    --slope ~/Desktop/QGIS_NEW/gis_timor/slope_deg.tif \
    --bbox 123.2 -10.5 125.3 -8.9 \
    --out ~/Desktop/QGIS_NEW/candidate_solar_timor.gpkg \
    --min-suitable 2 --max-slope-deg 15

# 2) Apply the resource assessment to a built dataset: village coordinates (from the
#    dataset manifest) -> developable solar MW -> village_generators.csv Max_Cap_MW,
#    plus an audit file village_solar_potential.csv.
python -m tools.ntt.solar_potential \
    --dataset data_indonesia/2030/timor_belu \
    --candidate candidate_solar_timor.gpkg --radius-km 5
# (or bake it into a fresh build: tools.ntt.build_timor ... --solar-cap)

# 3) The model enforces it. functions/optimizer.jl upper-bounds each village's new
#    solar build to its Max_Cap_MW (the VIL_ED_NEW loop). Max_Cap_MW = 0 = unbounded.
julia run_model.jl jobs/timor_belu_test/config.json
```

**Verified (Belu, 81 villages):** the land caps (per-village 0.9–4.5 GW within 5 km;
10 coordinate-less villages → regional median) enter the LP as variable upper bounds
(Gurobi reports `Bounds range [2e+02, 4e+03]`) and the `gridvillage` run solves to
the same optimum as the uncapped reference ($8.3597634 M) — i.e. at 5 km the ceiling
is a non-binding guardrail, as intended for villages serving sub-MW local demand.

## Usage

```bash
# reproduce the industrial-park output (validation / calibration)
python tools/resource_siting.py --validate --radius-km 15

# run on a points CSV (needs id + lat/lon columns)
python tools/resource_siting.py --points villages.csv --radius-km 5 --out village_siting.csv
```

Source layers default to `~/Desktop/QGIS_NEW` (override with `--gis-dir`).

## Aggregation modes

- **`buffer`** (default): sum the suitable-land `solar_MW` within `--radius-km`
  of the point, **area-clipped** — each candidate polygon is weighted by the
  fraction of its area inside the buffer, so large contiguous suitable regions
  are not over-counted (full-polygon summing inflated village figures ~100x).
  Land can be shared between nearby points. For villages use a small radius
  (2–10 km) — a village develops nearby land, not a smelter-scale catchment.
- **`allocate`**: assign each candidate polygon to its single nearest point
  (Voronoi) and sum per point. Partitions all land with no double-counting.

## Validation status

Reproduces the existing `solar_capacity_by_industrial_parks.csv`:

- **Grid proximity: exact** — HubDist correlation 1.000, median Δ 0.06 km.
- **Solar capacity: exact for near-grid parks** (11/17 at 15 km buffer). The
  remaining parks are remote or co-located (Delong Phase I/II/III share a site);
  the original park run mixed a fixed buffer with nearest-allocation, so no
  single mode reproduces all 17. For villages, pick one consistent mode + radius
  — the point is a reproducible rule, not replicating a partly-manual process.

## Data gap for the NTT / Timor case study — RESOLVED

> The default `candidate_solar_vector.gpkg` and `idn_slope.tif` are clipped at
> lat ≈ −9.0 and cover **none** of Timor. This is now fixed: `dem_slope.py` +
> `candidate_land.py` build `candidate_solar_timor.gpkg` for the region (step 1
> above), and `resource_siting.py --candidate candidate_solar_timor.gpkg` (or
> `tools.ntt.solar_potential`) uses it. The rest of this section is the diagnosis
> and method, kept for the record.

The candidate-solar and slope layers were built around the industrial parks
(Sumatra/Java/Kalimantan/Sulawesi/Maluku) and **clipped at latitude ≈ −9.0**,
which **excludes most of the Timor case-study region** (Kupang −10.2, Soe −9.9,
Sabu −10.5, Rote −10.7). Coverage of the inputs over NTT:

| Layer | Covers NTT? |
|-------|:-----------:|
| Substations (grid proximity) | ✅ yes — HubDist works for Timor today |
| GHI (solar resource raster) | ✅ yes (to −11.2) |
| Land cover | ✅ yes (to −11.0) |
| **Slope (`idn_slope.tif`)** | ❌ **no — stops at −9.1** |
| **Candidate solar (composite)** | ❌ **no — stops at −9.0** |

So `resource_siting.py` returns correct `hubdist_km` for Timor but
`solar_MW = 0` there, because the candidate layer is absent.

**Candidate-solar layer for NTT — now reproducible.** `tools/candidate_land.py`
builds it from the three inputs (land cover `suitable` score ∩ slope ≤ threshold,
× PV density), matching the `DN`/`area_m2`/`solar_MW` schema. Validated for Timor:

```bash
python tools/dem_slope.py --bbox 123.4 -10.5 125.2 -9 --out-dir gis_timor
python tools/candidate_land.py --landcover ~/Desktop/QGIS_NEW/idn_land_cover.shp \
    --slope gis_timor/slope_deg.tif --bbox 123.4 -10.5 125.2 -9 \
    --out gis_timor/candidate_solar_vector.gpkg --min-suitable 2 --max-slope-deg 15
# -> ~9,600 km2 suitable, ~598 GW technical potential over the Timor extent;
#    resource_siting.py then gives realistic per-village MW (e.g. Kupang ~3.4 GW within 5 km).
```

`--min-suitable` controls strictness (2 = incl. shrub/savannah; 3 = only
settlement/farm/bare land). The total is *technical* potential and vastly exceeds
the RUEN realistic figure — expected; the per-village buffered value is what
feeds the model.

**Historical note:** the only missing raw input was **slope**. `tools/dem_slope.py`
produces it — it downloads the public
Copernicus GLO-30 DEM (no credentials) for a bbox and computes a slope raster +
suitability mask:

```bash
python tools/dem_slope.py --bbox 121 -11 125 -8.5 --out-dir gis_ntt --max-slope-deg 15
```

With slope in hand, re-run the suitability composite (GHI × land cover × slope —
GHI and land cover already cover NTT) to produce candidate-solar polygons for the
region, then `resource_siting.py` runs unchanged. For the *temporal* solar
resource (hourly CF profiles), see `docs/solar_resource_geodata.md`.

## GIS inputs and version control

The GIS layers live **outside the repo** in `~/Desktop/QGIS_NEW` (≈47 GB total).
Only a handful are inputs to this module:

| File (in `~/Desktop/QGIS_NEW`) | Role | Used by | Size |
|---|---|---|---|
| `idn_land_cover.shp` (+ `.dbf/.shx/.prj/.cpg/.qix`) | land cover with `suitable` score (0/2/3) | `candidate_land.py` | ~612 MB |
| `substations_projected.shp` (+ sidecars) | nearest-substation for `hubdist_km` | `resource_siting.py` | ~7 MB |
| `candidate_solar_timor.gpkg` | **derived** suitable-land + `solar_MW` (the layer the siting reads) | `resource_siting.py`, `tools.ntt.solar_potential` | ~23 MB |
| `gis_timor/slope_deg.tif`, `dem_mosaic.tif`, `dem_tiles/` | **derived** slope + DEM (intermediate) | `candidate_land.py` | ~1 GB |
| `candidate_solar_vector.gpkg`, `parks_projected_new.gpkg`, `solar_capacity_by_industrial_parks.csv` | `--validate` only (industrial parks) | `resource_siting.py --validate` | ~9.5 MB |

**Do not commit the rasters/large shapefiles.** They exceed normal-git limits and
are reproducible: `dem_slope.py` re-downloads the public Copernicus GLO-30 DEM and
`candidate_land.py` rebuilds `candidate_solar_timor.gpkg` from land cover + slope.
For a teammate to run the model without a GIS stack, share just the two small
**outputs** that are already in the repo — `village_generators.csv` (with the caps)
and `village_solar_potential.csv` (the audit). To let them re-run the *siting*
without rebuilding the layer, share `candidate_solar_timor.gpkg` (~23 MB) and
`substations_projected.*` (~7 MB) via Git LFS or a data release — not plain git.
