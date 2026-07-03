#!/usr/bin/env python3
"""Wire ERA5 hourly solar CF into a dataset's village_generators_variability.csv.

The model runs on 8 representative weeks (CORRESPONDING_WEEKS, 168 h each =
1344 rows). This slices those weeks out of the ERA5 full-year CF
(village_solar_cf_hourly.csv, 8760 h) and overwrites the solar (`plts_*`)
columns in village_generators_variability.csv, leaving diesel/battery flat.

Villages are matched by order: the k-th `village_*` column in the CF maps to the
k-th `plts_*` column in the variability file (both are in village 1..N order).

Usage:
  python -m tools.ntt.wire_era5_solar \
      --cf solar_era5/village_solar_cf_hourly.csv \
      --dataset data_indonesia/2030/timor_era5
"""
import argparse
import csv

CORRESPONDING_WEEKS = [2, 9, 16, 24, 32, 40, 46, 52]
HOURS_PER_PERIOD = 168


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cf", required=True, help="village_solar_cf_hourly.csv (8760 h)")
    ap.add_argument("--dataset", required=True, help="dataset dir to patch")
    ap.add_argument("--weeks", default=",".join(map(str, CORRESPONDING_WEEKS)))
    a = ap.parse_args()
    weeks = [int(x) for x in a.weeks.split(",")]

    cf = list(csv.reader(open(a.cf)))
    cfh, cfd = cf[0], cf[1:]
    vcols = [j for j, n in enumerate(cfh) if n.startswith("village_")]

    # slice the representative weeks (in order) out of the 8760-h series
    sliced = []
    for w in weeks:
        for d in range((w - 1) * HOURS_PER_PERIOD, w * HOURS_PER_PERIOD):
            sliced.append([cfd[d][j] for j in vcols])
    assert len(sliced) == len(weeks) * HOURS_PER_PERIOD

    vg = a.dataset.rstrip("/") + "/village_generators_variability.csv"
    var = list(csv.reader(open(vg)))
    vh, vd = var[0], var[1:]
    pcols = [j for j, n in enumerate(vh) if n.startswith("plts_")]
    assert len(vd) == len(sliced), f"variability rows {len(vd)} != sliced {len(sliced)}"
    assert len(pcols) == len(vcols), f"plts cols {len(pcols)} != CF villages {len(vcols)}"

    for r in range(len(vd)):
        for k, pc in enumerate(pcols):
            vd[r][pc] = f"{float(sliced[r][k]):.5f}"

    with open(vg, "w", newline="") as f:
        csv.writer(f).writerows([vh] + vd)
    print(f"patched {vg}: {len(pcols)} solar cols x {len(vd)} rows "
          f"from ERA5 weeks {weeks}")


if __name__ == "__main__":
    main()
