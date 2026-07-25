"""CostCalculatorService — the reusable cost seam.

Costs a Site's GridConnection flows against a Tariff, per interval and independent of
resolution. Iteration 2's battery scenario re-runs this same service on a battery-adjusted
GridConnection, which is why it lives here rather than in the CLI.
"""
from __future__ import annotations

from datetime import date, datetime, time, tzinfo
from decimal import Decimal

from energy_sim.domain.cost import CostBreakdown
from energy_sim.domain.money import Money
from energy_sim.domain.site import Site
from energy_sim.domain.tariff import Tariff


class CostCalculatorService:
    def calculate(self, site: Site, tariff: Tariff) -> CostBreakdown:
        import_cost = Money.zero()
        export_credit = Money.zero()
        peak_import_kwh = 0.0
        offpeak_import_kwh = 0.0

        for gi in site.grid.intervals():
            ts = gi.ts_utc
            import_kwh = gi.import_energy.kwh
            export_kwh = gi.export_energy.kwh

            import_cost += Money.from_cents(tariff.import_rate(ts) * Decimal(str(import_kwh)))
            export_credit += Money.from_cents(tariff.export_rate(ts) * Decimal(str(export_kwh)))

            if tariff.is_peak(ts):
                peak_import_kwh += import_kwh
            else:
                offpeak_import_kwh += import_kwh

        return CostBreakdown(
            import_cost=import_cost,
            export_credit=export_credit,
            supply_charge=self._supply_charge(site, tariff),
            peak_import_kwh=peak_import_kwh,
            offpeak_import_kwh=offpeak_import_kwh,
        )

    @staticmethod
    def _supply_charge(site: Site, tariff: Tariff) -> Money:
        """Sum the daily supply charge over each distinct LOCAL billing day in the data.

        Aurora bills the fixed charge per local calendar day. Counting UTC dates instead
        overcharges by exactly one day per month, because a 30-day local billing month spans
        31 distinct UTC dates — worth $1.51 on June 2026, which is most of what was left of
        that month's residual once CT bias was calibrated out.
        """
        tz = tariff.billing_timezone
        dates = {gi.ts_utc.astimezone(tz).date() for gi in site.grid.intervals()}
        total = Money.zero()
        for d in dates:
            total += Money.from_cents(tariff.supply_charge_per_day(_local_midday(d, tz)))
        return total


def _local_midday(d: date, tz: tzinfo) -> datetime:
    """A datetime inside local calendar date ``d``, for period/rate lookup by date."""
    return datetime.combine(d, time(12, 0), tzinfo=tz)
