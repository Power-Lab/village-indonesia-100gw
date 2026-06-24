"""Aquaculture / pond farming village calculator — STUB.

No dedicated workbook has been supplied for the **aquaculture** archetype yet, so this
calculator inherits the residential-only default recipe from :class:`Calculator`
(households x 3.4 kWh/day + solar/battery sizing). When the partner provides the
aquaculture calculator, translate it here following the same sheet-by-sheet pattern as
``fishing.py`` and the guide in docs/calculators/README.md.

Productive loads to model for this archetype (typical):
    pumping/aeration, water circulation, hatchery, cold chain.
"""

from __future__ import annotations

from .base import Calculator


class AquacultureCalculator(Calculator):
    archetype = "aquaculture"

    # TODO(partner): override productive_kwh_per_hh_year (or demand()/sizing()/
    # costs()) from the aquaculture workbook. Until then the default recipe applies.
