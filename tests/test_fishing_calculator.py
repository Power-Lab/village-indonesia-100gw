"""Validate the fishing calculator reproduces the KDKMP workbook headline figures.

These are the numbers a partner can read directly off
`Kalkulator Desa Perikanan KDKMP_v6_editable.xlsx` (200-KK worked example), so
this test is the proof that the Python translation is faithful.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.ntt.calculators.fishing import FishingCalculator
from tools.ntt.calculators.base import Village


def _demo_village():
    return Village(kabupaten="-", kecamatan="-", desa="KDKMP demo",
                   households=200, ghi=5.34, archetype="fishing")


def test_annual_demand():
    calc = FishingCalculator()
    d = calc.demand(_demo_village())
    assert round(d.annual_kwh) == 500234          # 🐟·r58
    assert round(d.residential_kwh) == 248200     # 🐟·r57
    assert round(d.productive_kwh) == 252034      # 🐟·r56


def test_sizing():
    calc = FishingCalculator()
    v = _demo_village()
    s = calc.sizing(v, calc.demand(v))
    assert abs(s.solar_kwp - 356.9) < 0.1         # 🐟·r59
    assert abs(s.battery_kwh - 713.8) < 0.2       # 🐟·r60
    assert abs(s.detail["equipment_total_juta"] - 744.35) < 0.01   # 💰·r54

    equipment = {item["id"]: item for item in s.equipment}
    assert len(equipment) == 16
    assert equipment["AP1"]["units"] == 4                 # 💰·H30
    assert equipment["AP4"]["units"] == 84                # 💰·H34
    assert equipment["AP5"]["units"] == 3                 # 💰·H35
    assert equipment["AP6"]["units"] == 2                 # 💰·H37
    assert equipment["AP7"]["total_juta"] == 110          # 💰·J38
    assert equipment["AP14"]["units"] == 125              # 💰·H47
    assert equipment["AP15"]["units"] == 0                # inactive in 🐟·F47


def test_equipment_respects_village_production_overrides():
    """Equipment formulas must use the village override, not workbook defaults."""
    calc = FishingCalculator()
    v = _demo_village()
    v.extras = {"fish_profit_target_juta": 1660.0,
                "ice_profit_target_juta": 2190.0}
    d = calc.demand(v)
    equipment = {item["id"]: item for item in calc.sizing(v, d).equipment}
    assert equipment["AP1"]["units"] == 8
    assert equipment["AP5"]["units"] == 5
    assert equipment["AP6"]["units"] == 4


def test_investment():
    calc = FishingCalculator()
    v = _demo_village()
    s = calc.sizing(v, calc.demand(v))
    plts = calc.plts_investment_juta(v, s)
    assert abs(plts["total"] - 7899.8) < 0.5      # 💰·r71
    total = plts["total"] + s.detail["equipment_total_juta"]
    assert abs(total - 8644.15) < 1.0             # 💰·r76


def test_revenue_models():
    calc = FishingCalculator()
    v = _demo_village()
    s = calc.sizing(v, calc.demand(v))
    rev = calc.revenue(v, s).models
    assert abs(rev["model1_ipp"]["elec_revenue_juta"] - 308.144) < 0.1   # Pendapatan·r15 M1
    assert abs(rev["model3_owns_all"]["kdkmp_capex_juta"] - 8644.15) < 1.0  # Pendapatan·r31 M3


if __name__ == "__main__":
    for fn in [test_annual_demand, test_sizing,
               test_equipment_respects_village_production_overrides,
               test_investment, test_revenue_models]:
        fn()
        print(f"PASS {fn.__name__}")
