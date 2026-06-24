"""Fishing-village calculator — Python translation of the KDKMP workbook.

`Kalkulator Desa Perikanan KDKMP_v6_editable.xlsx` reimplemented sheet-by-sheet.
Every default below is the workbook's own input; line references (sheet · row)
and the original Indonesian source citations are kept inline so a partner can
diff this program against their spreadsheet. The validation test
(`tests/test_fishing_calculator.py`) checks the headline figures match.

Sheet map:
  📖 Asumsi Rantai Pasok          -> SUPPLY_CHAIN (AP1..AP16 kWh/ton table)
  🐟 Kalkulator Kebutuhan Listrik -> demand()
  💰 Kapasitas & Investasi        -> sizing() + costs()
  Kalkulator Pendapatan           -> revenue()

Run standalone to reproduce the workbook:
    python -m tools.ntt.calculators.fishing
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .base import Calculator, Village, DemandResult, SizingResult, CostResult, RevenueResult
from ..archetypes import SHAPE_FISHING


# --------------------------------------------------------------------------- #
# Sheet 📖 — supply-chain electricity intensity (kWh per ton of fish sold).
# (id, name_en, kwh_per_ton, active_by_default).  "active" mirrors column F.
# --------------------------------------------------------------------------- #
@dataclass
class Activity:
    id: str
    name_en: str
    kwh_per_ton: float
    active: bool


SUPPLY_CHAIN = [
    Activity("AP1",  "Electric boat charging",            140.0, True),
    Activity("AP2",  "LED fishing lights / attractor",     20.0, True),
    Activity("AP3",  "Navigation & fish finder",            7.5, False),
    Activity("AP4",  "Landing-site & auction (TPI) lights", 10.0, True),
    Activity("AP5",  "Weighing & sorting conveyor",          5.0, True),
    Activity("AP6",  "Ice-making machine",                 100.0, True),
    Activity("AP7",  "Cold storage (-18 C)",               112.5, True),
    Activity("AP8",  "Blast freezing (-35 C)",             180.0, False),
    Activity("AP9",  "Filleting & cutting machine",         16.5, False),
    Activity("AP10", "Electric fish dryer",                550.0, False),
    Activity("AP11", "Canning / vacuum packing",            37.5, False),
    Activity("AP12", "Clean-water pump",                     4.5, True),
    Activity("AP13", "Live-fish pond aeration",             22.5, False),
    Activity("AP14", "Processing-facility lighting",         6.5, True),
    Activity("AP15", "Refrigerated delivery vehicle",       15.0, False),
    Activity("AP16", "Retail display chiller",               8.0, False),
]


class FishingCalculator(Calculator):
    archetype = "fishing"

    # ---- Sheet 🐟 section A: village profile defaults (row references) ------
    residential_kwh_per_hh_day = 3.4          # 🐟·r6  (ESMAP MTF Tier 4)
    fish_profit_target_juta = 830.0           # 🐟·r10 (juta Rp/yr net profit from fish)
    profit_per_ton_fish_juta = 7.5            # 🐟·r11
    ice_profit_target_juta = 1095.0           # 🐟·r15 (juta Rp/yr net profit from ice)
    profit_per_ton_ice_juta = 0.5             # 🐟·r16
    ice_to_fish_ratio = 1.0                   # 🐟·r19 (ton ice per ton fish)
    kwh_per_ton_ice = 100.0                   # 🐟·r53

    solar_cf = 0.16                           # 🐟·r59 (PLTS capacity factor)
    battery_to_pv_ratio = 2.0                 # 🐟·r60 (BESS kWh per PV kWp)

    # ---- Sheet 💰 section A: technical sizing assumptions -------------------
    fishing_days = 200                        # 💰·r5
    ice_plant_days = 365                      # 💰·r6
    catch_per_trip_kg = 150                   # 💰·r7
    trips_per_boat_year = 200                 # 💰·r8
    boat_motor_kw = 3.7                       # 💰·r9
    boat_hours_per_trip = 6                   # 💰·r10
    ice_unit_ton_day = 4                      # 💰·r13
    ice_buffer = 1.25                         # 💰·r14
    cold_store_days = 5                       # 💰·r15
    cold_store_density = 0.4                  # 💰·r16 (ton/m3)
    cold_store_buffer = 1.3                   # 💰·r17
    water_m3_per_ton_fish = 3                 # 💰·r18
    water_m3_per_ton_ice = 1.1                # 💰·r19
    tpi_area_m2 = 200                         # 💰·r20
    processing_area_m2 = 300                  # 💰·r21
    lighting_w_per_m2 = 15                    # 💰·r22

    # ---- Sheet 💰 section D: PLTS component costs (Rp juta per unit) --------
    pv_panel_juta_per_kwp = 5.5
    pv_inverter_juta_per_kwp = 1.8
    pv_mounting_juta_per_kwp = 0.8
    pv_bos_juta_per_kwp = 0.5
    bess_battery_juta_per_kwh = 3.5
    bess_bos_juta_per_kwh = 1.0
    distribution_juta_per_hh = 6.0
    epc_fraction = 0.12                       # of PV hardware
    commissioning_juta = 50.0

    # ---- Sheet Kalkulator Pendapatan: tariffs -------------------------------
    tariff_member_rp_kwh = 2000
    tariff_ipp_rp_kwh = 1300
    collection_efficiency = 0.88

    # ----------------------------------------------------------------- demand
    def _production(self, village: Village):
        """Fish & ice tonnage from the profit targets (🐟 section A)."""
        ex = village.extras
        fish_profit = ex.get("fish_profit_target_juta", self.fish_profit_target_juta)
        ice_profit = ex.get("ice_profit_target_juta", self.ice_profit_target_juta)
        fish_ton = fish_profit / self.profit_per_ton_fish_juta          # 🐟·r12
        ice_ton = ice_profit / self.profit_per_ton_ice_juta             # 🐟·r17
        ice_for_fish = fish_ton * self.ice_to_fish_ratio                # 🐟·r19
        ice_external = max(0.0, ice_ton - ice_for_fish)                 # 🐟·r20
        return fish_ton, ice_ton, ice_for_fish, ice_external

    def demand(self, village: Village) -> DemandResult:
        fish_ton, ice_ton, ice_for_fish, ice_external = self._production(village)
        active_kwh_per_ton = sum(a.kwh_per_ton for a in SUPPLY_CHAIN if a.active)  # 🐟·r52
        # Productive load: per-ton-fish activities (incl. ice for fish via AP6) +
        # ice sold to non-fishing buyers.
        productive_fish = active_kwh_per_ton * fish_ton                 # 🐟·r54
        productive_ice = self.kwh_per_ton_ice * ice_external            # 🐟·r55
        productive = productive_fish + productive_ice                   # 🐟·r56
        residential = village.households * self.residential_kwh_per_hh_day * 365.0  # 🐟·r57
        annual = productive + residential                               # 🐟·r58

        mean_shape = sum(SHAPE_FISHING) / len(SHAPE_FISHING)
        peak_mw = (annual / 1000.0) / (8760.0 * mean_shape) if annual else 0.0
        return DemandResult(
            annual_kwh=annual, residential_kwh=residential, productive_kwh=productive,
            demand_shape=SHAPE_FISHING, peak_mw=peak_mw,
            detail={"fish_ton": fish_ton, "ice_ton": ice_ton,
                    "ice_external_ton": ice_external,
                    "active_kwh_per_ton": active_kwh_per_ton,
                    "productive_fish_kwh": productive_fish,
                    "productive_ice_kwh": productive_ice},
        )

    # ----------------------------------------------------------------- sizing
    def _equipment(self, village: Village, fish_ton, ice_ton, ice_external):
        """Productive-asset list with quantities & prices (💰 section B).
        Returns list of {id,name,units,price_juta,total_juta,active}."""
        fish_kg = fish_ton * 1000.0
        ice_day = ice_ton / 365.0 * 365.0  # target es/hari basis ~6 ton/day from r18
        ice_per_day = self.ice_profit_target_juta / self.profit_per_ton_ice_juta / 365.0
        items = []

        def add(act_id, units, price_juta, active):
            items.append({"id": act_id, "units": units, "price_juta": price_juta,
                          "total_juta": (units * price_juta) if active else 0.0,
                          "active": active})

        # epsilon-safe ceiling: the spreadsheet's CEILING() is exact, so guard
        # against float drift (e.g. 4.5/0.036 = 125.0000001 -> 126).
        def iceil(x):
            return math.ceil(round(x, 6))

        amap = {a.id: a for a in SUPPLY_CHAIN}
        boats = iceil(fish_kg / (self.catch_per_trip_kg * self.trips_per_boat_year))
        add("AP1", boats, 50.0, amap["AP1"].active)            # electric boats
        add("AP2", boats, 2.0, amap["AP2"].active)             # LED sets (1/boat)
        add("AP3", boats, 5.0, amap["AP3"].active)             # nav (inactive)
        tpi_kw = self.tpi_area_m2 * self.lighting_w_per_m2 / 1000.0
        add("AP4", iceil(tpi_kw / 0.036), 0.15, amap["AP4"].active)  # 36W LED panels
        add("AP5", 3, 10.0, amap["AP5"].active)                # weighing/sorting
        ice_cap = ice_per_day * self.ice_buffer
        add("AP6", iceil(ice_cap / self.ice_unit_ton_day), 180.0, amap["AP6"].active)
        cold_vol = (fish_ton * self.cold_store_days / 365.0
                    / self.cold_store_density * self.cold_store_buffer)
        add("AP7", iceil(cold_vol), 22.0, amap["AP7"].active)
        add("AP12", 1, 5.0, amap["AP12"].active)               # water pump
        proc_kw = self.processing_area_m2 * self.lighting_w_per_m2 / 1000.0
        add("AP14", iceil(proc_kw / 0.036), 0.15, amap["AP14"].active)
        return items

    def sizing(self, village: Village, demand: DemandResult) -> SizingResult:
        solar_kwp = demand.annual_kwh / (8760.0 * self.solar_cf) if demand.annual_kwh else 0.0
        battery_kwh = solar_kwp * self.battery_to_pv_ratio
        diesel_mw = round(demand.peak_mw * 1.1, 4)
        fish_ton = demand.detail["fish_ton"]
        ice_ton = demand.detail["ice_ton"]
        equipment = self._equipment(village, fish_ton, ice_ton,
                                    demand.detail["ice_external_ton"])
        return SizingResult(solar_kwp=solar_kwp, battery_kwh=battery_kwh,
                            diesel_mw=diesel_mw, equipment=equipment,
                            detail={"equipment_total_juta": sum(e["total_juta"] for e in equipment)})

    # ------------------------------------------------------------------ costs
    def plts_investment_juta(self, village: Village, sizing: SizingResult) -> dict:
        """PLTS+BESS+distribution+EPC investment (💰 section D), Rp juta."""
        kwp, kwh, hh = sizing.solar_kwp, sizing.battery_kwh, village.households
        pv_hw = kwp * (self.pv_panel_juta_per_kwp + self.pv_inverter_juta_per_kwp
                       + self.pv_mounting_juta_per_kwp + self.pv_bos_juta_per_kwp)
        bess = kwh * (self.bess_battery_juta_per_kwh + self.bess_bos_juta_per_kwh)
        distribution = hh * self.distribution_juta_per_hh
        epc = self.epc_fraction * pv_hw
        commissioning = self.commissioning_juta
        total = pv_hw + bess + distribution + epc + commissioning
        return {"pv_hardware": pv_hw, "bess": bess, "distribution": distribution,
                "epc": epc, "commissioning": commissioning, "total": total}

    def costs(self, sizing: SizingResult) -> CostResult:
        from .. import costs as C
        return CostResult(
            solar_inv_per_mwyr=C.annualise_idr_per_kw(
                (self.pv_panel_juta_per_kwp + self.pv_inverter_juta_per_kwp
                 + self.pv_mounting_juta_per_kwp + self.pv_bos_juta_per_kwp) * 1e6, "solar"),
            solar_fom_per_mwyr=C.fixed_om_per_mwyr(8.6e6, "solar"),
            battery_inv_per_mwyr=C.annualise_idr_per_kw(self.bess_bos_juta_per_kwh * 1e6, "battery"),
            battery_inv_per_mwhyr=C.annualise_idr_per_kwh(self.bess_battery_juta_per_kwh * 1e6, "battery"),
            battery_fom_per_mwyr=C.fixed_om_per_mwyr(4.5e6, "battery"),
            capex_idr={
                "solar_juta": sizing.solar_kwp * 8.6,
                "battery_juta": sizing.battery_kwh * 4.5,
                "equipment_juta": sizing.detail.get("equipment_total_juta", 0.0),
            },
        )

    # ---------------------------------------------------------------- revenue
    def revenue(self, village: Village, sizing: SizingResult) -> RevenueResult:
        """Electricity-sales + CAPEX exposure for the three business models
        (Kalkulator Pendapatan sections A & C). Financial returns (NPV/IRR,
        sections E–F) are intentionally left to be extended with the partner."""
        demand = self.demand(village)
        plts = self.plts_investment_juta(village, sizing)
        equip = sizing.detail.get("equipment_total_juta", 0.0)
        coll = self.collection_efficiency
        # Annual electricity revenue (Rp juta) — section A r15/r17.
        m1_rev = (self.tariff_member_rp_kwh - self.tariff_ipp_rp_kwh) * demand.annual_kwh * coll / 1e6
        m2_rev = self.tariff_member_rp_kwh * demand.annual_kwh * coll / 1e6
        m3_rev = self.tariff_member_rp_kwh * demand.residential_kwh * coll / 1e6
        return RevenueResult(models={
            "model1_ipp":   {"elec_revenue_juta": round(m1_rev, 3), "kdkmp_capex_juta": 0.0},
            "model2_owns_plts": {"elec_revenue_juta": round(m2_rev, 3),
                                 "kdkmp_capex_juta": round(plts["total"], 3)},
            "model3_owns_all":  {"elec_revenue_juta": round(m3_rev, 3),
                                 "kdkmp_capex_juta": round(plts["total"] + equip, 3)},
        })


# Standalone reproduction of the workbook's worked example (200-KK village).
if __name__ == "__main__":
    calc = FishingCalculator()
    v = Village(kabupaten="-", kecamatan="-", desa="KDKMP demo", households=200,
                ghi=5.34, archetype="fishing")
    d = calc.demand(v)
    s = calc.sizing(v, d)
    plts = calc.plts_investment_juta(v, s)
    print(f"Annual demand:        {d.annual_kwh:,.0f} kWh/yr "
          f"(residential {d.residential_kwh:,.0f} + productive {d.productive_kwh:,.0f})")
    print(f"PLTS sizing:          {s.solar_kwp:,.1f} kWp")
    print(f"BESS sizing:          {s.battery_kwh:,.1f} kWh")
    print(f"Productive equipment: Rp {s.detail['equipment_total_juta']:,.2f} juta")
    print(f"PLTS system investment: Rp {plts['total']:,.1f} juta")
    print(f"TOTAL investment:     Rp {plts['total'] + s.detail['equipment_total_juta']:,.1f} juta "
          f"({(plts['total'] + s.detail['equipment_total_juta'])/1000:,.2f} miliar)")
