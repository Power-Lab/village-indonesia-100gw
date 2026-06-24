"""Per-archetype calculator registry.

One calculator program per village archetype. Fishing is fully translated from
the KDKMP workbook; the other nine are stub modules that inherit the
residential-only default recipe until their workbooks are supplied. Adding a
real calculator = fill in that archetype's module + it is already registered
here (see docs/calculators/README.md).
"""

from __future__ import annotations

from .base import Calculator
from .fishing import FishingCalculator
from .aquaculture import AquacultureCalculator
from .rice import RiceCalculator
from .horticulture import HorticultureCalculator
from .plantation import PlantationCalculator
from .livestock import LivestockCalculator
from .forestry import ForestryCalculator
from .trade import TradeCalculator
from .manufacturing import ManufacturingCalculator
from .government import GovernmentCalculator

# archetype name -> Calculator instance
CALCULATORS: dict[str, Calculator] = {
    c.archetype: c for c in [
        FishingCalculator(),
        AquacultureCalculator(),
        RiceCalculator(),
        HorticultureCalculator(),
        PlantationCalculator(),
        LivestockCalculator(),
        ForestryCalculator(),
        TradeCalculator(),
        ManufacturingCalculator(),
        GovernmentCalculator(),
    ]
}
CALCULATORS.setdefault("default", Calculator())


def get_calculator(archetype: str) -> Calculator:
    """Return the calculator for an archetype, or the default recipe."""
    return CALCULATORS.get(archetype, CALCULATORS["default"])
