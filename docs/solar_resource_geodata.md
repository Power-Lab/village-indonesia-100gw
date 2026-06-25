# Solar Resource via geodata (alternative)

> **Note:** the project's primary solar-profile path is now **ERA5 direct** —
> see `docs/solar_resource_era5.md`. This geodata approach is kept as an
> alternative / cross-check; it wraps the same CDS backend but adds a fuller
> plane-of-array PV model.

`tools/solar_resource_geodata.py` builds **hourly solar PV capacity-factor
profiles per village** from reanalysis weather data, using
[GeodataTools/geodata](https://github.com/GeodataTools/geodata). This is the
*temporal* half of the solar resource — distinct from the *spatial* potential
(`tools/resource_siting.py`, which gives developable MW per village). Together:

| Question | Tool | Output → model input |
|----------|------|----------------------|
| How much solar can a village build? | `resource_siting.py` | `solar_MW` → village `Max_Cap_MW` |
| What does its output look like hour-by-hour? | `solar_resource_geodata.py` | hourly CF → `village_generators_variability.csv` |

Right now the model reuses island-level solar CF for villages; geodata lets you
generate **Timor-specific** profiles, and is the cleaner long-term source for any
region.

## Why geodata

geodata wraps the download + PV-modelling chain: it pulls ERA5 or MERRA-2,
subsets to a region/time (`Cutout`), and runs a tilted-irradiance PV model
(`convert.pv`) to produce capacity factors in [0, 1]. The same pipeline gives
wind (`convert.wind`) if village wind is added later.

## Prerequisites

geodata downloads data, so it needs an account + API credentials and network.
**Nothing is bundled** — the script is meant to be run by the analyst, not in CI.

- **`pip install geodata`** (already present in the project conda env as 0.1.0).
- **ERA5** (default, `--module era5`): a free [Copernicus CDS](https://cds.climate.copernicus.eu)
  account. Put your key in `~/.cdsapirc`:
  ```
  url: https://cds.climate.copernicus.eu/api
  key: <UID>:<API-KEY>
  ```
  geodata uses `cdsapi` (confirmed installed). First download of a year over the
  NTT bbox is tens of MB and can take a while as CDS queues the request.
- **MERRA-2** (`--module merra2`): a free [NASA Earthdata](https://urs.earthdata.nasa.gov)
  login in `~/.netrc`. Useful as an ERA5 cross-check.
- geodata caches raw data and cutouts under `~/.local/geodata` (and the cutout
  under `--out-dir/cutouts`), so reruns are cheap.

## Usage

```bash
python tools/solar_resource_geodata.py \
    --points villages.csv \          # id + lat/lon columns
    --year 2023 \
    --bbox 121 -11 125 -8.5 \        # NTT/Timor (default)
    --panel CSi \                    # bundled: CSi, CdTe, KANEKA
    --out-dir solar_ntt
```

Panel orientation defaults to a fixed tilt equal to the bbox-centre latitude,
equator-facing (azimuth 0 = North in the southern hemisphere). Override with
`--tilt` / `--azimuth`.

### Outputs (`--out-dir`)

- `village_solar_cf_hourly.csv` — 8760 hourly capacity factors, one column per
  village (`village_<id>`).
- `village_solar_annual.csv` — per village: `mean_cf`, `full_load_hours`. NTT is
  high-quality solar; expect mean CF ≈ 0.18–0.22 (FLH ≈ 1,600–1,900 h).

## Wiring into the model

`village_generators_variability.csv` uses the model's representative periods
(currently 8 weeks × 168 h = 1,344 hours, not full 8760). To connect:

1. Run this script → `village_solar_cf_hourly.csv` (full year).
2. Subset/average those 8760 hours to the **same representative weeks** the
   demand files use (the rep-period structure is defined in `demand.csv`; pick
   the same `corresponding_week` hours).
3. Write the result as the solar columns of `village_generators_variability.csv`,
   one column per village solar generator in `R_ID` order (see
   `data_indonesia/README.md` for the variability-file convention).

The annual `mean_cf` can also feed the spatial weighting in
`resource_siting.py` if you want per-village solar *quality* to modulate the
developable-MW figure (sunnier villages weighted up).

## Relationship to the existing data

- The QGIS folder already has a `GHI_Annual_kWhm2.tif` (annual solar resource)
  and an `era5_indonesia_2023.nc`. geodata is the better path because it goes
  all the way to **PV capacity factors with panel physics and hourly chronology**,
  not just annual irradiance, and it is fully scripted/reproducible rather than
  manual QGIS.
- For the land-suitability side (which land is buildable), see
  `docs/resource_siting.md` and `tools/dem_slope.py` (slope for NTT).
