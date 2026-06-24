# Adding an archetype calculator

Each village **archetype** (fishing, food crops, livestock, …) has its own
calculator: a Python program that reproduces that archetype's design
spreadsheet, turning a village's physical attributes into electricity demand,
equipment sizing, and cost. Fishing is done (`tools/ntt/calculators/fishing.py`,
translated from the KDKMP workbook); this guide is how to add the next one.

The goal is a **one-to-one, auditable translation** of the partner's spreadsheet
— same inputs, same formulas, same numbers — so results can be traced back to a
source the partner already trusts.

## The contract

Every calculator subclasses `Calculator` (`tools/ntt/calculators/base.py`) and
may override four methods. They run in order; each takes the previous result:

```python
class MyArchetypeCalculator(Calculator):
    archetype = "rice"          # must match the name in archetypes.REGISTRY

    def demand(self, village)         -> DemandResult   # annual kWh + hourly shape
    def sizing(self, village, demand) -> SizingResult   # PV kWp, BESS kWh, diesel, equipment
    def costs(self, sizing)           -> CostResult       # annualised USD/MW-yr (model-ready)
    def revenue(self, village, sizing)-> RevenueResult|None  # business models (NOT fed to the model)
```

- **`demand`** → `DemandResult(annual_kwh, residential_kwh, productive_kwh,
  demand_shape, peak_mw, detail)`. `peak_mw` must be derived so the shaped hourly
  series integrates to `annual_kwh` (the base class shows the formula).
- **`sizing`** → `SizingResult(solar_kwp, battery_kwh, diesel_mw, equipment, detail)`.
- **`costs`** → `CostResult(...)` with annualised USD/MW-yr figures. Use the
  helpers in `tools/ntt/costs.py` (`annualise_idr_per_kw`, `annualise_idr_per_kwh`,
  `fixed_om_per_mwyr`) — never hard-code USD.
- **`revenue`** is optional and documented-only; it keeps the Python program a
  faithful mirror of the whole workbook but is not consumed by the optimiser.

The base class already implements a **residential-only default** (households ×
3.4 kWh/day + solar/battery sizing). A stub archetype that doesn't override
anything simply uses that.

## Steps

1. **Get the workbook** for the archetype from the partner.
2. **Fill in the stub** `tools/ntt/calculators/<archetype>.py` (it already exists,
   subclassing `Calculator`). Translate sheet by sheet:
   - Put every spreadsheet input as a **class attribute with the workbook's own
     default value**, and a comment citing the sheet · cell (see `fishing.py`,
     e.g. `fish_profit_target_juta = 830.0   # 🐟·r10`).
   - Reproduce each formula in `demand` / `sizing` / `costs`. Keep intermediate
     quantities in the `detail` dict for debugging.
   - Guard spreadsheet `CEILING()` against float drift with
     `math.ceil(round(x, 6))` (a real bug we hit: `4.5/0.036 → 125.0000001`).
3. **Register it** — it is already wired into `tools/ntt/calculators/__init__.py`
   via its class; just confirm the `archetype` name matches `archetypes.REGISTRY`.
4. **Check assignment** — make sure `archetypes.REGISTRY[<name>].keywords` match
   the subsector/commodity strings the data uses for this archetype (test with
   `tools/ntt/sources.load_timor_villages`).
5. **Write a validation test** in `tests/` asserting the calculator reproduces the
   workbook's headline figures for its worked example (see
   `tests/test_fishing_calculator.py`). This is the proof of faithful translation.
6. **Document it** — add a `docs/calculators/<archetype>_<source>.md` like
   `fishing_KDKMP.md`: the sheet→function map, formulas, assumptions + sources,
   and an Excel-value-vs-Python-value validation table.

## What "faithful" means

A reviewer should be able to open the spreadsheet and this module side by side
and match: every input value, every formula, and the headline outputs (annual
kWh, PV kWp, BESS kWh, total investment) to within rounding. If the spreadsheet
has logic the optimiser doesn't use (revenue, IRR), translate it into `revenue()`
and document it — don't silently drop it.
