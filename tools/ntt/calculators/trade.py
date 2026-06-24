"""Trade / retail / services village calculator — STUB.

No dedicated workbook has been supplied for the **trade** archetype yet, so this
calculator inherits the residential-only default recipe from :class:`Calculator`
(households x 3.4 kWh/day + solar/battery sizing). When the partner provides the
trade calculator, translate it here following the same sheet-by-sheet pattern as
``fishing.py`` and the guide in docs/calculators/README.md.

Productive loads to model for this archetype (typical):
    retail refrigeration, lighting, POS/charging, small workshops.
"""

from __future__ import annotations

from .base import Calculator


class TradeCalculator(Calculator):
    archetype = "trade"

    # TODO(partner): override productive_kwh_per_hh_year (or demand()/sizing()/
    # costs()) from the trade workbook. Until then the default recipe applies.
