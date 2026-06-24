"""The calculator contract every archetype implements.

Each archetype's Excel calculator (the partner's spreadsheet) is reimplemented
as a Python `Calculator` subclass. They all share this interface so the
orchestrator (`tools.ntt.build_timor`) and the partner can use any archetype
uniformly, and so a new archetype is "drop in one file" work.

A `Calculator` maps a `Village` (its physical attributes, from the source
workbooks) to four results:

    demand(village)          -> DemandResult    # annual kWh + hourly load shape
    sizing(village, demand)  -> SizingResult    # PV kWp, BESS kWh, diesel, equipment
    costs(sizing)            -> CostResult       # capex + annualised USD/MW-yr
    revenue(village, sizing) -> RevenueResult    # business models (NOT fed to the optimizer)

Only demand/sizing/costs feed the capacity-expansion model; `revenue` exists so
the Python program faithfully mirrors the whole workbook for the partner.

The flow mirrors the KDKMP workbook sheets:
  Kalkulator Kebutuhan Listrik -> demand()
  Kapasitas & Investasi        -> sizing() + costs()
  Kalkulator Pendapatan        -> revenue()
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Village:
    """Physical attributes of one village, assembled by `tools.ntt.sources`."""
    kabupaten: str
    kecamatan: str
    desa: str
    households: int                 # total KK = PLN + non-PLN + unelectrified
    hh_pln: int = 0
    hh_nonpln: int = 0
    hh_unelectrified: int = 0
    ghi: float = 5.34               # kWh/m2/day
    lat: float | None = None
    lon: float | None = None
    archetype: str = "default"
    matched_ghi: bool = True        # False -> GHI was filled from the NTT mean
    extras: dict = field(default_factory=dict)  # archetype-specific overrides


@dataclass
class DemandResult:
    annual_kwh: float               # total village electricity demand per year
    residential_kwh: float
    productive_kwh: float
    demand_shape: list[float]       # 24 hour-of-day fractions of peak
    peak_mw: float                  # derived so the shaped series integrates to annual
    detail: dict = field(default_factory=dict)   # per-activity breakdown (kWh/yr)


@dataclass
class SizingResult:
    solar_kwp: float
    battery_kwh: float
    diesel_mw: float                # existing genset sized to peak
    equipment: list[dict] = field(default_factory=list)  # productive-asset line items
    detail: dict = field(default_factory=dict)


@dataclass
class CostResult:
    # Annualised, model-ready (USD).
    solar_inv_per_mwyr: float
    solar_fom_per_mwyr: float
    battery_inv_per_mwyr: float     # power component
    battery_inv_per_mwhyr: float    # energy component
    battery_fom_per_mwyr: float
    # Absolute overnight capex for reporting (IDR).
    capex_idr: dict = field(default_factory=dict)


@dataclass
class RevenueResult:
    """Business-model economics — documented for the partner, NOT used by the model."""
    models: dict = field(default_factory=dict)


class Calculator:
    """Base calculator. Subclasses override the four methods.

    The default implementation is a residential-only recipe used by every
    archetype that does not yet have a dedicated calculator."""

    archetype = "default"

    # Shared defaults (ESMAP MTF Tier 4 household consumption).
    residential_kwh_per_hh_day = 3.4
    productive_kwh_per_hh_year = 0.0     # archetypes add productive load here
    solar_cf = 0.16                      # annual PV capacity factor
    battery_to_pv_ratio = 2.0            # BESS kWh per PV kWp (rule of thumb)
    solar_idr_per_kwp = 8_600_000        # KDKMP PV all-in (Rp/kWp)
    battery_idr_per_kw = 0.0
    battery_idr_per_kwh = 4_500_000      # KDKMP BESS all-in (Rp/kWh)

    def demand(self, village: "Village") -> "DemandResult":
        from ..archetypes import REGISTRY
        residential = village.households * self.residential_kwh_per_hh_day * 365.0
        productive = village.households * self.productive_kwh_per_hh_year
        annual = residential + productive
        shape = REGISTRY[self.archetype].demand_shape
        mean_shape = sum(shape) / len(shape)
        peak_mw = (annual / 1000.0) / (8760.0 * mean_shape) if annual > 0 else 0.0
        return DemandResult(annual_kwh=annual, residential_kwh=residential,
                            productive_kwh=productive, demand_shape=shape,
                            peak_mw=peak_mw)

    def sizing(self, village: "Village", demand: "DemandResult") -> "SizingResult":
        solar_kwp = (demand.annual_kwh / (8760.0 * self.solar_cf)) if demand.annual_kwh else 0.0
        battery_kwh = solar_kwp * self.battery_to_pv_ratio
        diesel_mw = round(demand.peak_mw * 1.1, 4)   # existing genset covers peak + margin
        return SizingResult(solar_kwp=solar_kwp, battery_kwh=battery_kwh,
                            diesel_mw=diesel_mw)

    def costs(self, sizing: "SizingResult") -> "CostResult":
        from .. import costs as C
        return CostResult(
            solar_inv_per_mwyr=C.annualise_idr_per_kw(self.solar_idr_per_kwp, "solar"),
            solar_fom_per_mwyr=C.fixed_om_per_mwyr(self.solar_idr_per_kwp, "solar"),
            battery_inv_per_mwyr=C.annualise_idr_per_kw(self.battery_idr_per_kw, "battery"),
            battery_inv_per_mwhyr=C.annualise_idr_per_kwh(self.battery_idr_per_kwh, "battery"),
            battery_fom_per_mwyr=C.fixed_om_per_mwyr(self.battery_idr_per_kw or 1_000_000, "battery"),
            capex_idr={
                "solar": sizing.solar_kwp * self.solar_idr_per_kwp,
                "battery": sizing.battery_kwh * self.battery_idr_per_kwh,
            },
        )

    def revenue(self, village: "Village", sizing: "SizingResult") -> "RevenueResult | None":
        return None
