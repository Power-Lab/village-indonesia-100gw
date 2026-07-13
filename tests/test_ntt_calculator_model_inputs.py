"""Integration checks: calculator results become Julia model-input CSV values."""

import csv
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.ntt.build_timor import HOURS_PER_PERIOD, REP_PERIODS, SUB_WEIGHT, build
from tools.ntt.calculators.base import Village
from tools.ntt.calculators.fishing import FishingCalculator


def _rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def test_fishing_calculator_values_feed_model_inputs():
    village = Village(
        kabupaten="KUPANG", kecamatan="TEST", desa="FISHING TEST",
        households=200, ghi=5.34, lat=-10.0, lon=123.5,
        archetype="fishing",
    )
    calc = FishingCalculator()
    demand = calc.demand(village)
    sizing = calc.sizing(village, demand)
    costs = calc.costs(sizing)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        village_count, grid_peak = build([village], out, "2030")

        assert village_count == 1
        assert grid_peak == round(demand.peak_mw, 3)

        # DemandResult -> village_demand.csv. The representative-hour series,
        # annualised with the model's sample weight, must recover annual kWh.
        demand_rows = _rows(out / "village_demand.csv")
        assert len(demand_rows) == REP_PERIODS * HOURS_PER_PERIOD
        assert float(demand_rows[0]["demand_village1"]) == round(
            demand.peak_mw * demand.demand_shape[0], 6
        )
        annual_mwh = sum(float(r["demand_village1"]) for r in demand_rows) * (
            SUB_WEIGHT / HOURS_PER_PERIOD
        )
        assert abs(annual_mwh * 1000 - demand.annual_kwh) < 1.0

        # Demand peak and CostResult -> the diesel, solar, and battery rows in
        # village_generators.csv, which is read by the Julia input loader.
        generators = _rows(out / "village_generators.csv")
        diesel, solar, battery = generators
        assert float(diesel["Existing_Cap_MW"]) == round(
            max(demand.peak_mw * 1.1, 0.01), 4
        )
        assert float(solar["Inv_Cost_per_MWyr"]) == costs.solar_inv_per_mwyr
        assert float(solar["Fixed_OM_Cost_per_MWyr"]) == costs.solar_fom_per_mwyr
        assert float(battery["Inv_Cost_per_MWyr"]) == costs.battery_inv_per_mwyr
        assert float(battery["Inv_Cost_per_MWhyr"]) == costs.battery_inv_per_mwhyr


if __name__ == "__main__":
    test_fishing_calculator_values_feed_model_inputs()
    print("PASS test_fishing_calculator_values_feed_model_inputs")
