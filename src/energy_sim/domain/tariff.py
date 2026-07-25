"""Tariff domain: peak-window classification, time-of-use rates, period selection.

Rates are c/kWh (Decimal); supply is c/day.

The peak window is evaluated in the BILLING TIMEZONE, because that is how Aurora bills it:
local Mon-Fri, 7-10am and 4-9pm. `infra/vmalert/powerflow.yml` instead encodes it as fixed
UTC hours (Mon-Fri, [6,11) union [21,24)), which is wrong twice over:

  * The weekday test lands on the UTC date, but the 21:00-24:00Z block is the NEXT local day.
    So UTC-Friday 21-24Z is Saturday morning locally (billed off-peak, charged peak) and
    UTC-Sunday 21-24Z is Monday morning locally (billed peak, charged off-peak). Over June
    2026 this misclassified 27 hours — every single classifier mismatch against Aurora's own
    hourly split, and worth -$1.05 on that month's bill.
  * The fixed offset ignores daylight saving, so both blocks sit an hour off for the ~half of
    the year Tasmania is on AEDT.

Evaluating in the billing timezone fixes both. This deliberately diverges from powerflow.yml
until the same fix is applied there; Aurora's billed data is the ground truth, not the metrics
layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from decimal import Decimal


@dataclass(frozen=True)
class PeakWindow:
    """When time-of-use import is charged at the peak rate, in local billing time.

    Weekdays use the ISO convention (Mon=1..Sun=7), so Mon-Fri is {1,2,3,4,5}. Hours are the
    local hour a period starts, so 4-9pm is {16,17,18,19,20}.
    """

    timezone: tzinfo
    local_weekdays: frozenset[int]
    local_hours: frozenset[int]

    def contains(self, dt_utc: datetime) -> bool:
        local = dt_utc.astimezone(self.timezone)
        return local.isoweekday() in self.local_weekdays and local.hour in self.local_hours


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

    def __init__(
        self,
        periods: list[TariffPeriod],
        peak_window: PeakWindow,
        billing_timezone: tzinfo | None = None,
    ) -> None:
        if not periods:
            raise ValueError("Tariff requires at least one period")
        self._periods = sorted(periods, key=lambda p: p.valid_from)
        self._peak_window = peak_window
        # Aurora uses TWO clocks: billing days are local calendar days (DST-aware), while the
        # time-of-use window is priced on fixed AEST year-round. Defaults to the window's clock
        # so a tariff without daily charges needs no extra argument.
        self._billing_timezone = billing_timezone or peak_window.timezone

    @property
    def billing_timezone(self) -> tzinfo:
        """The zone whose calendar days the fixed daily charge is billed on (DST-aware)."""
        return self._billing_timezone

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
