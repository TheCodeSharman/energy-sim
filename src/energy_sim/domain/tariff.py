"""Tariff domain: peak-window classification, time-of-use rates, period selection.

Mirrors infra/vmalert/powerflow.yml's `pf:is_peak` / `pf:import_rate_c_kwh` so the sim's
cost model matches the metrics layer. Rates are c/kWh (Decimal); supply is c/day.

CAVEAT (documented, not fixed): the peak window is expressed in fixed UTC hours, matching
the vmalert source, which assumes a fixed AEST offset and so ignores daylight saving.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class PeakWindow:
    """When time-of-use import is charged at the peak rate.

    Weekdays use the Prometheus ``day_of_week()`` convention (Sun=0..Sat=6) so the config
    values match powerflow.yml. Python's ``datetime.weekday()`` (Mon=0..Sun=6) is mapped on.
    """

    utc_weekdays: frozenset[int]
    utc_hours: frozenset[int]

    def contains(self, dt_utc: datetime) -> bool:
        prometheus_dow = (dt_utc.weekday() + 1) % 7  # Mon=0..Sun=6 -> Sun=0..Sat=6
        return prometheus_dow in self.utc_weekdays and dt_utc.hour in self.utc_hours


@dataclass(frozen=True)
class TariffPeriod:
    """Rates in force from ``valid_from`` until the next period begins."""

    valid_from: date
    peak_c_kwh: Decimal
    offpeak_c_kwh: Decimal
    export_c_kwh: Decimal
    supply_c_day: Decimal


class Tariff:
    """A time-of-use tariff: ordered rate periods plus a peak-window rule."""

    def __init__(self, periods: list[TariffPeriod], peak_window: PeakWindow) -> None:
        if not periods:
            raise ValueError("Tariff requires at least one period")
        self._periods = sorted(periods, key=lambda p: p.valid_from)
        self._peak_window = peak_window

    def is_peak(self, dt_utc: datetime) -> bool:
        return self._peak_window.contains(dt_utc)

    def import_rate(self, dt_utc: datetime) -> Decimal:
        period = self._period_for(dt_utc)
        return period.peak_c_kwh if self.is_peak(dt_utc) else period.offpeak_c_kwh

    def peak_rate(self, dt_utc: datetime) -> Decimal:
        """The peak import rate of the active period (independent of the hour)."""
        return self._period_for(dt_utc).peak_c_kwh

    def offpeak_rate(self, dt_utc: datetime) -> Decimal:
        """The off-peak import rate of the active period (independent of the hour)."""
        return self._period_for(dt_utc).offpeak_c_kwh

    def export_rate(self, dt_utc: datetime) -> Decimal:
        return self._period_for(dt_utc).export_c_kwh

    def supply_charge_per_day(self, dt_utc: datetime) -> Decimal:
        return self._period_for(dt_utc).supply_c_day

    def _period_for(self, dt_utc: datetime) -> TariffPeriod:
        when = dt_utc.date()
        applicable = [p for p in self._periods if p.valid_from <= when]
        if not applicable:
            raise ValueError(
                f"No tariff period covers {when!s}; earliest is {self._periods[0].valid_from!s}"
            )
        return applicable[-1]  # latest period whose valid_from has passed
