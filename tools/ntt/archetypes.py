"""Village archetype registry, auto-assignment, and shared load/solar profiles.

A village *archetype* is its dominant economic activity (fishing, rice,
livestock, ...). Each archetype has a dedicated **calculator** (see
`tools.ntt.calculators`) that turns village attributes into electricity demand,
equipment sizing, and cost. This module holds the lightweight metadata used to
*assign* a village to an archetype and the hour-of-day shapes shared across
calculators.

Fishing is fully implemented from the KDKMP workbook; the other nine archetypes
are registered here with keyword-matching rules and fall back to a
residential-only default recipe until their own calculators are supplied. The
canonical list of ten archetypes should be confirmed with the partner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# --------------------------------------------------------------- demand shapes
# Fraction of daily peak by hour-of-day (24 values). Calculators may override.

SHAPE_RESIDENTIAL = [0.25, 0.22, 0.20, 0.20, 0.22, 0.30, 0.45, 0.50, 0.55, 0.60,
                     0.62, 0.60, 0.58, 0.55, 0.50, 0.45, 0.50, 0.80, 1.00, 0.95,
                     0.80, 0.60, 0.40, 0.30]
# Fishing: ice-making / cold storage run hard through the day + evening peak.
SHAPE_FISHING = [0.55, 0.52, 0.50, 0.50, 0.55, 0.65, 0.80, 0.90, 0.95, 1.00,
                 1.00, 0.98, 0.95, 0.92, 0.88, 0.85, 0.85, 0.92, 1.00, 0.95,
                 0.85, 0.75, 0.65, 0.58]

PERF_RATIO = 0.80           # PV performance ratio (GHI -> AC energy yield)
DEFAULT_GHI = 5.34          # NTT mean GHI (kWh/m2/day); fallback for unmatched villages


def solar_cf_builder(ghi_kwh_m2_day: float):
    """Return cf(t) -> hourly solar capacity factor for a 1-based hour index,
    scaled so the average daily energy yield matches the village GHI
    (peak-sun-hours = GHI x performance ratio)."""
    target_daily_full_load_hours = ghi_kwh_m2_day * PERF_RATIO
    raw = [math.sin(math.pi * (h - 6) / 12) ** 1.3 if 6 <= h <= 18 else 0.0
           for h in range(24)]
    s = sum(raw) or 1.0
    scale = target_daily_full_load_hours / s

    def cf(t: int) -> float:
        return round(min(1.0, raw[(t - 1) % 24] * scale), 4)

    return cf


# --------------------------------------------------------------- archetypes

@dataclass
class Archetype:
    """Metadata for assigning a village to an archetype and picking its load shape.
    The economic/sizing logic lives in the matching calculator, not here."""
    name: str
    keywords: list[str] = field(default_factory=list)   # matched against potensi-desa text
    demand_shape: list[float] = field(default_factory=lambda: SHAPE_RESIDENTIAL)
    label: str = ""                                     # human-readable (English)


# Order = assignment priority (first keyword match wins). `default` is the
# fallback and is never matched by keyword.
REGISTRY: dict[str, Archetype] = {
    "fishing":       Archetype("fishing", ["perikanan", "ikan", "nelayan", "tangkap"],
                               SHAPE_FISHING, "Fishing / capture fisheries"),
    "aquaculture":   Archetype("aquaculture", ["budidaya", "tambak", "rumput laut"],
                               SHAPE_FISHING, "Aquaculture / pond farming"),
    "rice":          Archetype("rice", ["tanaman pangan", "padi", "sawah", "jagung",
                                        "ubi", "kacang"],
                               label="Food crops (rice / maize)"),
    "horticulture":  Archetype("horticulture", ["hortikultura", "sayur", "buah"],
                               label="Horticulture"),
    "plantation":    Archetype("plantation", ["perkebunan", "kelapa", "kopi", "kakao",
                                              "jambu mete", "cengkeh"],
                               label="Plantation / estate crops"),
    "livestock":     Archetype("livestock", ["peternakan", "ternak", "sapi", "babi",
                                             "kambing", "unggas"],
                               label="Livestock"),
    "forestry":      Archetype("forestry", ["kehutanan", "hutan", "kayu"],
                               label="Forestry"),
    "trade":         Archetype("trade", ["perdagangan", "eceran", "reparasi"],
                               label="Trade / retail / services"),
    "manufacturing": Archetype("manufacturing", ["industri pengolahan", "industri"],
                               label="Manufacturing / processing"),
    "government":    Archetype("government", ["administrasi pemerintahan", "pendidikan",
                                             "konstruksi", "jasa"],
                               label="Government / services / other"),
    "default":       Archetype("default", [], label="Residential-only (fallback)"),
}


def assign_archetype(*texts: str) -> Archetype:
    """Pick an archetype by keyword-matching a village's classification strings,
    in PRIORITY ORDER — the first (most authoritative) text that matches any
    archetype wins. Pass the specific subsector first, then commodity, then the
    broad sector. Within a text, REGISTRY order breaks ties. Falls back to
    `default`."""
    for text in texts:
        if not text:
            continue
        hay = str(text).lower()
        for arch in REGISTRY.values():
            if arch.name != "default" and any(kw in hay for kw in arch.keywords):
                return arch
    return REGISTRY["default"]
