"""EVCostService — the EV's actual cost on the bill, from the Zappi's measured split.

Grid-charged kWh cost the time-of-use import rate for their interval; solar-charged kWh cost the
forgone export credit (the FiT given up by diverting that surplus into the car instead of selling
it). Same shape as CostCalculatorService, same Tariff — the EV is just another costed device.
"""
from __future__ import annotations

from dataclasses import dataclass

from energy_sim.domain.ev_charger import EVCharger
from energy_sim.domain.money import Money
from energy_sim.domain.tariff import Tariff


@dataclass(frozen=True)
class EVCostBreakdown:
    grid_cost: Money
    forgone_export_credit: Money

    @property
    def total(self) -> Money:
        return self.grid_cost + self.forgone_export_credit


class EVCostService:
    def calculate(self, ev: EVCharger, tariff: Tariff) -> EVCostBreakdown:
        grid_cost = Money.zero()
        forgone_export_credit = Money.zero()
        for ci in ev.intervals():
            grid_cost += Money.from_cents(tariff.import_rate(ci.ts_utc)) * ci.grid_kwh
            forgone_export_credit += Money.from_cents(tariff.export_rate(ci.ts_utc)) * ci.solar_kwh
        return EVCostBreakdown(grid_cost=grid_cost, forgone_export_credit=forgone_export_credit)
