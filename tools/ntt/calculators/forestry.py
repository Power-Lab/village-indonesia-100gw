"""Forestry village calculator — STUB.

No dedicated workbook has been supplied for the **forestry** archetype yet, so this
calculator inherits the residential-only default recipe from :class:`Calculator`
(households x 3.4 kWh/day + solar/battery sizing). When the partner provides the
forestry calculator, translate it here following the same sheet-by-sheet pattern as
``fishing.py`` and the guide in docs/calculators/README.md.

Productive loads to model for this archetype (typical):
    sawmilling, planing, drying kilns, workshop tools.
"""

from __future__ import annotations

from .base import Calculator


class ForestryCalculator(Calculator):
    archetype = "forestry"

    # TODO(partner): override productive_kwh_per_hh_year (or demand()/sizing()/
    # costs()) from the forestry workbook. Until then the default recipe applies.
