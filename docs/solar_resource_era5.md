# Solar Resource — ERA5 direct

`tools/solar_resource_era5.py` builds **hourly solar PV capacity-factor profiles
per village** straight from ERA5, with a transparent PV model and no third-party
resource library. This is the primary solar-profile path for the project;
`docs/solar_resource_geodata.md` describes the geodata-based alternative.

It produces the *temporal* solar resource (CF shape over time) that the model
needs for `village_generators_variability.csv`. The *spatial* potential
(developable MW per village) comes separately from `tools/resource_siting.py`.

## Why direct ERA5

- One transparent, auditable PV equation (below) — no geodata version coupling.
- Uses the same Copernicus CDS backend, so no extra account beyond `~/.cdsapirc`.
- Can also ingest an ERA5 NetCDF you already have (`--era5-file`).

## Prerequisites

- `cdsapi` (installed) + a free [Copernicus CDS](https://cds.climate.copernicus.eu)
  account. Credentials in `~/.cdsapirc`:
  ```
  url: https://cds.climate.copernicus.eu/api
  key: <UID>:<API-KEY>
  ```
  (This project's machine already has `~/.cdsapirc` configured.)
- The first CDS request for a full year over the NTT bbox queues server-side and
  can take minutes to tens of minutes; the file is cached in `--out-dir`.

## The PV model (auditable)

```
GHI(t) = ssrd(t) / 3600                       # ERA5 ssrd is J/m2 accumulated per hour -> mean W/m2
Tcell  = T2m + (NOCT - 20)/800 * GHI          # cell temperature from air temp + irradiance
CF(t)  = clip(GHI/1000, 0, 1) * PR * (1 + gamma*(Tcell - 25))
```

Parameters (all CLI flags, with defaults): `--pr 0.80` (performance ratio),
`--noct 45` (nominal operating cell temp, degC), `--gamma -0.004` (power temp
coefficient per degC).

This is a **GHI-based fixed-array** estimate: it captures irradiance and
temperature derating but not full plane-of-array (tilt/azimuth) transposition.
For planning — where the CF *shape* and seasonal/diurnal structure matter most —
it is adequate and easy to defend. If a specific annual yield is required, use
`--target-flh` to scale CF so mean full-load hours hit a target (e.g. a Global
Solar Atlas figure for the site). Validated on synthetic input: clear-sky midday
CF ≈ 0.59, night 0, implied ≈ 1,600 FLH for a sunny tropical day — consistent
with NTT (mean CF ≈ 0.18–0.22).

## Usage

```bash
# download ERA5 for NTT and compute per-village CF
python tools/solar_resource_era5.py --points villages.csv --year 2023 \
    --bbox 121 -11 125 -8.5 --out-dir solar_ntt

# or reuse an ERA5 file you already downloaded
python tools/solar_resource_era5.py --points villages.csv \
    --era5-file my_era5_2023.nc --out-dir solar_ntt
```

### Outputs (`--out-dir`)

- `village_solar_cf_hourly.csv` — 8760 hourly CF, one column per village.
- `village_solar_annual.csv` — per village `mean_cf`, `full_load_hours`.

CDS may deliver the NetCDF inside a zip; the script detects this (magic bytes)
and unzips transparently. A truncated download fails loudly — re-request it.

### Time zone — important

ERA5 is in **UTC**. The model's demand profiles are local time, so the solar CF
must be shifted or the PV peak lands hours away from the load (corrupting the
standalone-vs-grid comparison). `--utc-offset` rolls the series to local time;
the default **+8 (WITA)** is correct for NTT/Timor. Use +7 (WIB, western
Indonesia) or +9 (WIT, eastern) for other regions. Verified on real Timor ERA5:
after +8 the PV peak lands at local hour 12 with a clean midday bell curve.

## Wiring into the model

`village_generators_variability.csv` uses the model's representative periods
(8 weeks × 168 h = 1,344 h), not full 8760. To connect:

1. Run this script → `village_solar_cf_hourly.csv` (full year).
2. Subset those hours to the **same representative weeks** the demand files use
   (defined by `corresponding_week` in `demand.csv`).
3. Write the result as the solar columns of `village_generators_variability.csv`,
   one per village solar generator in `R_ID` order (see `data_indonesia/README.md`).

`mean_cf` can also weight the developable-MW figure from `resource_siting.py`
(sunnier villages weighted up), and `--target-flh` keeps annual energy honest.

## Related

- Land suitability / developable MW: `docs/resource_siting.md`, `tools/dem_slope.py`.
- geodata-based alternative for the same CF profiles: `docs/solar_resource_geodata.md`.
