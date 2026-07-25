"""CostBreakdown — the outcome of costing a period's grid flows against a tariff."""
from __future__ import annotations

from dataclasses import dataclass

from energy_sim.domain.money import Money


@dataclass(frozen=True)
class CostBreakdown:
    import_cost: Money
    export_credit: Money
    supply_charge: Money
    peak_import_kwh: float
    offpeak_import_kwh: float

    @property
    def usage_cost(self) -> Money:
        """Import cost net of export credit, EXCLUDING the fixed supply charge.

        This is the figure compared against Aurora's usage dollars (which are usage-only).
        """
        return self.import_cost - self.export_credit

    @property
    def net_cost(self) -> Money:
        """Full cost including the daily supply charge."""
        return self.usage_cost + self.supply_charge
