# Fishing calculator — KDKMP workbook → `fishing.py`

How `Kalkulator Desa Perikanan KDKMP_v6_editable.xlsx` was reimplemented as
`tools/ntt/calculators/fishing.py`, sheet by sheet, with a validation table
proving the Python reproduces the workbook. This is the worked template for the
other nine archetype calculators.

The English copy of the workbook is
`data_indonesia/source_ntt/english/Fishing_Village_Calculator_KDKMP_EN.xlsx`.

## Sheet → function map

| Workbook sheet | Python | What it does |
|----------------|--------|--------------|
| 📖 Asumsi Rantai Pasok | `SUPPLY_CHAIN` table | AP1–AP16: electricity intensity (kWh per ton of fish) for each supply-chain activity, and which are active. |
| 🐟 Kalkulator Kebutuhan Listrik | `demand()` | Village electricity demand: residential + productive (fish + ice). |
| 💰 Kapasitas & Investasi | `sizing()` + `plts_investment_juta()` + `costs()` | Equipment sizing, PV/BESS sizing, and investment. |
| Kalkulator Pendapatan | `revenue()` | Three business models (electricity sales + CAPEX exposure). Financial returns (NPV/IRR) not yet translated. |

## The demand chain (sheet 🐟)

Worked example: a 200-household fishing village.

1. **Production from profit targets**
   - fish = `fish_profit_target / profit_per_ton_fish` = 830 / 7.5 = **110.67 ton/yr** (🐟·r12)
   - ice = `ice_profit_target / profit_per_ton_ice` = 1095 / 0.5 = **2190 ton/yr** (🐟·r17)
   - ice for fish = fish × 1:1 = 110.67 ton; ice sold externally = 2190 − 110.67 = **2079.33 ton** (🐟·r19–20)
2. **Productive load**
   - active supply-chain intensity = Σ active AP = **398.5 kWh/ton fish** (🐟·r52)
   - productive(fish) = 398.5 × 110.67 = **44,101 kWh** (🐟·r54)
   - productive(ice sold) = 100 kWh/ton × 2079.33 = **207,933 kWh** (🐟·r55)
3. **Residential** = households × 3.4 kWh/day × 365 = 200 × 1241 = **248,200 kWh** (🐟·r57)
4. **Total village demand** = 44,101 + 207,933 + 248,200 = **500,234 kWh/yr** (🐟·r58)
5. **Indicative PV** = 500,234 / (8760 × 0.16) = **356.9 kWp**; **BESS** = 2 × PV = **713.8 kWh** (🐟·r59–60)

## Supply-chain activities (sheet 📖, `SUPPLY_CHAIN`)

The 16 activities, kWh per ton of fish, with the 8 active in the worked example:

| ID | Activity | kWh/ton | Active |
|----|----------|--------:|:------:|
| AP1 | Electric boat charging | 140 | ✓ |
| AP2 | LED fishing lights | 20 | ✓ |
| AP3 | Navigation & fish finder | 7.5 | |
| AP4 | Landing-site / auction lighting | 10 | ✓ |
| AP5 | Weighing & sorting | 5 | ✓ |
| AP6 | Ice-making machine | 100 | ✓ |
| AP7 | Cold storage (−18 °C) | 112.5 | ✓ |
| AP8 | Blast freezing (−35 °C) | 180 | |
| AP9 | Filleting & cutting | 16.5 | |
| AP10 | Electric fish dryer | 550 | |
| AP11 | Canning / vacuum packing | 37.5 | |
| AP12 | Clean-water pump | 4.5 | ✓ |
| AP13 | Live-fish pond aeration | 22.5 | |
| AP14 | Processing-facility lighting | 6.5 | ✓ |
| AP15 | Refrigerated delivery vehicle | 15 | |
| AP16 | Retail display chiller | 8 | |

Active sum = 140+20+10+5+100+112.5+4.5+6.5 = **398.5 kWh/ton**.

## Equipment & investment (sheet 💰)

`sizing()` reproduces the equipment quantities (boats = ceil(fish kg ÷
(catch/trip × trips/yr)); ice-maker units = ceil(ice/day × buffer ÷ unit size);
cold-store volume; lighting panels; etc.) at the workbook's unit prices →
**Rp 744.35 juta** of productive assets.

`plts_investment_juta()` reproduces the PV system:

| Component | Basis | Rp juta |
|-----------|-------|--------:|
| PV hardware (panel+inverter+mounting+BOS) | 8.6 juta/kWp × 356.9 | 3,069.4 |
| BESS (battery + BOS) | 4.5 juta/kWh × 713.8 | 3,212.1 |
| LV distribution | 6 juta/KK × 200 | 1,200.0 |
| EPC | 12 % of PV hardware | 368.3 |
| Commissioning | lump sum | 50.0 |
| **PLTS system total** | | **7,899.8** |

Total investment = 7,899.8 + 744.35 = **Rp 8,644 juta (≈ 8.64 miliar)**.

## Validation table (Excel → Python)

Asserted by `tests/test_fishing_calculator.py` (all pass):

| Quantity | Workbook | `fishing.py` | Match |
|----------|---------:|-------------:|:-----:|
| Annual demand (kWh/yr) | 500,234 | 500,234 | ✓ |
| Residential (kWh/yr) | 248,200 | 248,200 | ✓ |
| Productive (kWh/yr) | 252,034 | 252,034 | ✓ |
| PV (kWp) | 356.9 | 356.9 | ✓ |
| BESS (kWh) | 713.8 | 713.8 | ✓ |
| Productive equipment (Rp juta) | 744.35 | 744.35 | ✓ |
| PLTS system investment (Rp juta) | 7,899.8 | 7,899.8 | ✓ |
| Total investment (Rp juta) | 8,644.15 | 8,644.2 | ✓ (rounding) |
| Model 1 electricity revenue (Rp juta) | 308.14 | 308.14 | ✓ |
| Model 3 KDKMP CAPEX (Rp juta) | 8,644.15 | 8,644.2 | ✓ |

Reproduce it yourself:
```bash
python -m tools.ntt.calculators.fishing      # prints the worked example
python -m pytest tests/test_fishing_calculator.py
```

## What is and isn't translated

- **Translated & validated:** demand chain, equipment & PV/BESS sizing,
  investment, and the per-business-model electricity revenue + CAPEX exposure.
- **Not yet translated:** the full financial model in *Kalkulator Pendapatan*
  rows 35+ (OPEX detail, grant recovery, NPV/IRR/payback, BESS replacement). The
  workbook itself notes these are "belum terkoneksi dengan DCF helper" (not yet
  wired to the DCF helper). These do not feed the optimiser; translate them into
  `revenue()` when the partner wants the full financial picture in Python.
- **Feeds the optimiser:** only `demand()`/`sizing()`/`costs()`. `revenue()` is
  documentation-only.
