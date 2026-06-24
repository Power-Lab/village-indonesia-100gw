"""IDR -> annualised USD cost conversion.

The source calculators (and the KDKMP workbook) quote equipment costs as
*overnight* capital in Indonesian Rupiah (Rp), per kWp for PV, per kWh for
batteries, etc. The capacity-expansion model expects **annualised investment
cost in USD per MW-year** (and per MWh-year for storage energy). This module is
the single place that conversion happens, so every calculator and the partner
documentation can point at one set of assumptions.

Conversion, per component:

    usd_per_kw   = idr_per_kw / FX_RATE          # Rp -> USD
    usd_per_mw   = usd_per_kw * 1000             # per-kW -> per-MW
    crf          = r (1+r)^n / ((1+r)^n - 1)     # capital recovery factor
    inv_per_mwyr = usd_per_mw * crf              # overnight -> annualised

All defaults are documented and overridable so a partner can re-run with their
own exchange rate / discount rate / asset lives.
"""

from __future__ import annotations

# ---- Default assumptions (override via CLI / function args) -----------------
FX_RATE = 16_000.0          # Rp per USD (mid-2024..2026 working assumption)
DISCOUNT_RATE = 0.10        # real discount rate for annualisation
LIFETIME_YEARS = {          # economic life per technology (years)
    "solar": 25,
    "battery": 12,
    "diesel": 15,
    "grid": 30,             # distribution / interconnection assets
}
FIXED_OM_FRACTION = {       # annual fixed O&M as a fraction of overnight capex
    "solar": 0.02,
    "battery": 0.02,
    "diesel": 0.03,
    "grid": 0.01,
}


def crf(rate: float, years: int) -> float:
    """Capital recovery factor: fraction of overnight capex paid per year."""
    if rate == 0:
        return 1.0 / years
    f = (1.0 + rate) ** years
    return rate * f / (f - 1.0)


def annualise_idr_per_kw(idr_per_kw: float, tech: str,
                         fx: float = FX_RATE, rate: float = DISCOUNT_RATE) -> float:
    """Rp/kWp (or Rp/kW) overnight capital -> USD/MW-yr annualised investment."""
    usd_per_mw = (idr_per_kw / fx) * 1000.0
    return round(usd_per_mw * crf(rate, LIFETIME_YEARS[tech]))


def annualise_idr_per_kwh(idr_per_kwh: float, tech: str = "battery",
                          fx: float = FX_RATE, rate: float = DISCOUNT_RATE) -> float:
    """Rp/kWh overnight capital -> USD/MWh-yr annualised investment (storage energy)."""
    usd_per_mwh = (idr_per_kwh / fx) * 1000.0
    return round(usd_per_mwh * crf(rate, LIFETIME_YEARS[tech]))


def fixed_om_per_mwyr(idr_per_kw: float, tech: str, fx: float = FX_RATE) -> float:
    """Annual fixed O&M (USD/MW-yr) as a fraction of overnight capex."""
    usd_per_mw = (idr_per_kw / fx) * 1000.0
    return round(usd_per_mw * FIXED_OM_FRACTION[tech])


def idr_to_usd(idr: float, fx: float = FX_RATE) -> float:
    """Plain currency conversion (for reporting absolute capex in USD)."""
    return idr / fx
