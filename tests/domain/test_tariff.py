"""Tariff domain: peak-window rule, period selection by date, rate lookup.

The peak window mirrors infra/vmalert/powerflow.yml `pf:is_peak` exactly: UTC Mon-Fri,
hours [6,11) union [21,24). day_of_week()/hour() are UTC there, so we test in UTC.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from energy_sim.domain.tariff import PeakWindow, Tariff, TariffPeriod

UTC = timezone.utc

# Standard Aurora Tariff 93 peak window (Prometheus day_of_week convention: Sun=0..Sat=6).
PEAK_WINDOW = PeakWindow(utc_weekdays=frozenset({1, 2, 3, 4, 5}),
                         utc_hours=frozenset({6, 7, 8, 9, 10, 21, 22, 23}))

FY2025 = TariffPeriod(valid_from=date(2025, 7, 1), peak_c_kwh=Decimal("31.948"),
                      offpeak_c_kwh=Decimal("14.876"), export_c_kwh=Decimal("8.782"),
                      supply_c_day=Decimal("0.0"))
FY2026 = TariffPeriod(valid_from=date(2026, 7, 1), peak_c_kwh=Decimal("36.1878"),
                      offpeak_c_kwh=Decimal("17.02"), export_c_kwh=Decimal("9.276"),
                      supply_c_day=Decimal("172.3469"))
TARIFF = Tariff(periods=[FY2025, FY2026], peak_window=PEAK_WINDOW)


# --- PeakWindow ---------------------------------------------------------------

def test_weekday_within_peak_hours_is_peak():
    # 2026-06-01 is a Monday; 06:00 UTC is inside [6,11).
    assert PEAK_WINDOW.contains(datetime(2026, 6, 1, 6, 0, tzinfo=UTC)) is True


def test_weekday_evening_utc_hour_is_peak():
    # 21:00 UTC on a weekday is inside the [21,24) block.
    assert PEAK_WINDOW.contains(datetime(2026, 6, 1, 21, 0, tzinfo=UTC)) is True


def test_weekday_outside_peak_hours_is_offpeak():
    # 05:00 and 11:00 UTC are outside the peak blocks.
    assert PEAK_WINDOW.contains(datetime(2026, 6, 1, 5, 0, tzinfo=UTC)) is False
    assert PEAK_WINDOW.contains(datetime(2026, 6, 1, 11, 0, tzinfo=UTC)) is False


def test_weekend_is_never_peak():
    # 2026-06-06 is a Saturday.
    assert PEAK_WINDOW.contains(datetime(2026, 6, 6, 6, 0, tzinfo=UTC)) is False


# --- Tariff period selection & rates -----------------------------------------

def test_import_rate_peak_in_fy2025():
    assert TARIFF.import_rate(datetime(2026, 6, 1, 6, 0, tzinfo=UTC)) == Decimal("31.948")


def test_import_rate_offpeak_in_fy2025():
    assert TARIFF.import_rate(datetime(2026, 6, 1, 5, 0, tzinfo=UTC)) == Decimal("14.876")


def test_import_rate_uses_later_period_after_boundary():
    # 2026-07-02 is a Thursday; 06:00 UTC is peak, and the FY2026 period applies.
    assert TARIFF.import_rate(datetime(2026, 7, 2, 6, 0, tzinfo=UTC)) == Decimal("36.1878")


def test_export_rate_by_period():
    assert TARIFF.export_rate(datetime(2026, 6, 15, 0, 0, tzinfo=UTC)) == Decimal("8.782")
    assert TARIFF.export_rate(datetime(2026, 7, 15, 0, 0, tzinfo=UTC)) == Decimal("9.276")


def test_supply_charge_by_period():
    assert TARIFF.supply_charge_per_day(datetime(2026, 6, 15, 0, 0, tzinfo=UTC)) == Decimal("0.0")
    assert TARIFF.supply_charge_per_day(datetime(2026, 7, 15, 0, 0, tzinfo=UTC)) == Decimal("172.3469")


def test_date_before_earliest_period_raises():
    with pytest.raises(ValueError):
        TARIFF.import_rate(datetime(2025, 6, 1, 6, 0, tzinfo=UTC))


def test_peak_rate_returns_period_peak_regardless_of_hour():
    # Even at an off-peak hour, peak_rate returns the period's peak rate.
    assert TARIFF.peak_rate(datetime(2026, 6, 1, 5, 0, tzinfo=UTC)) == Decimal("31.948")


def test_offpeak_rate_returns_period_offpeak_regardless_of_hour():
    assert TARIFF.offpeak_rate(datetime(2026, 6, 1, 6, 0, tzinfo=UTC)) == Decimal("14.876")
