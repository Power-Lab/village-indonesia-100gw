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

## ⚠️ Data gap for the NTT / Timor case study

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
