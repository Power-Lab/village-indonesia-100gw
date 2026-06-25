#!/usr/bin/env python3
"""Controlled diversity stress-test (EXP-003).

Rewrites half the villages' hourly demand in a copied dataset to a midday-peaking
shape (energy-preserved per village), leaving the other half as the real
residential/evening profile. Isolates the effect of load-SHAPE diversity on the
value of grid coordination — everything else (magnitudes, solar, costs,
connection costs) is identical to the real Timor data.

Usage: python3 make_diverse_demand.py <village_demand.csv>
"""
import csv
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else \
    "data_indonesia/2030/timor_diverse/village_demand.csv"


def midday_shape(h):
    # baseline 0.3 + a daytime bump peaking at noon (zero ramp outside 06–18h)
    return 0.3 + 0.7 * max(0.0, 1.0 - abs(h - 12) / 6.0)


with open(SRC) as f:
    rows = list(csv.reader(f))

header, data = rows[0], rows[1:]
n = len(data)

vcols = [i for i, c in enumerate(header) if c.startswith("demand_village")]
# reshape every other village -> midday load; the rest keep their real profile
selected = [c for k, c in enumerate(vcols) if k % 2 == 0]

# hour-of-day from the 'hour' column (rep-periods are 168h = 24-aligned)
hour_idx = header.index("hour")
hod = [int(float(data[r][hour_idx])) % 24 for r in range(n)]
shape_sum = sum(midday_shape(h) for h in hod)

for ci in selected:
    col_sum = sum(float(data[r][ci]) for r in range(n))
    for r in range(n):
        data[r][ci] = f"{col_sum * midday_shape(hod[r]) / shape_sum:.6f}"

with open(SRC, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(header)
    w.writerows(data)

print(f"villages={len(vcols)}  reshaped_to_midday={len(selected)}  "
      f"left_residential={len(vcols)-len(selected)}  rows={n}")
