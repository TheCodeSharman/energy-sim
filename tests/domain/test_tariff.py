"""Tariff domain: peak-window rule, period selection by date, rate lookup.

The peak window is Aurora Tariff 93 as billed: LOCAL Mon-Fri, 7-10am and 4-9pm. It is
evaluated in the billing timezone, not in fixed UTC hours — see the docstring in tariff.py
for why the fixed-UTC form (which infra/vmalert/powerflow.yml still uses) misbills.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from energy_sim.domain.tariff import PeakWindow, Tariff, TariffPeriod

UTC = timezone.utc
HOBART = ZoneInfo("Australia/Hobart")
AEST = ZoneInfo("Etc/GMT-10")  # fixed UTC+10, no DST — the clock Aurora prices on

# Standard Aurora Tariff 93 peak window (ISO weekdays: Mon=1..Sun=7).
PEAK_WINDOW = PeakWindow(timezone=AEST,
                         local_weekdays=frozenset({1, 2, 3, 4, 5}),
                         local_hours=frozenset({7, 8, 9, 16, 17, 18, 19, 20}))

FY2025 = TariffPeriod(valid_from=date(2025, 7, 1), peak_c_kwh=Decimal("31.948"),
                      offpeak_c_kwh=Decimal("14.876"), export_c_kwh=Decimal("8.782"),
                      supply_c_day=Decimal("0.0"))
FY2026 = TariffPeriod(valid_from=date(2026, 7, 1), peak_c_kwh=Decimal("36.1878"),
                      offpeak_c_kwh=Decimal("17.02"), export_c_kwh=Decimal("9.276"),
                      supply_c_day=Decimal("172.3469"))
TARIFF = Tariff(periods=[FY2025, FY2026], peak_window=PEAK_WINDOW)


# --- PeakWindow ---------------------------------------------------------------

def test_weekday_afternoon_block_is_peak():
    # Mon 2026-06-01 16:00 AEST = 06:00 UTC.
    assert PEAK_WINDOW.contains(datetime(2026, 6, 1, 6, 0, tzinfo=UTC)) is True


def test_weekday_morning_block_is_peak():
    # Tue 2026-06-02 07:00 AEST = Mon 21:00 UTC.
    assert PEAK_WINDOW.contains(datetime(2026, 6, 1, 21, 0, tzinfo=UTC)) is True


def test_hours_outside_both_blocks_are_offpeak():
    # Mon 15:00 and 21:00 AEST — either side of the afternoon block.
    assert PEAK_WINDOW.contains(datetime(2026, 6, 1, 5, 0, tzinfo=UTC)) is False
    assert PEAK_WINDOW.contains(datetime(2026, 6, 1, 11, 0, tzinfo=UTC)) is False


def test_weekend_is_never_peak():
    # Sat 2026-06-06 16:00 AEST = 06:00 UTC.
    assert PEAK_WINDOW.contains(datetime(2026, 6, 6, 6, 0, tzinfo=UTC)) is False


# The two cases a fixed-UTC window gets wrong. Aurora's own hourly split proves both:
# these were 27 of 27 classifier mismatches over June 2026.

def test_monday_morning_peak_is_caught_despite_being_sunday_in_utc():
    # Mon 2026-06-01 07:00 AEST = Sun 2026-05-31 21:00 UTC. UTC says weekend; Aurora bills peak.
    assert PEAK_WINDOW.contains(datetime(2026, 5, 31, 21, 0, tzinfo=UTC)) is True


def test_saturday_morning_is_offpeak_despite_being_friday_in_utc():
    # Sat 2026-06-06 07:00 AEST = Fri 2026-06-05 21:00 UTC. UTC says weekday; Aurora bills off-peak.
    assert PEAK_WINDOW.contains(datetime(2026, 6, 5, 21, 0, tzinfo=UTC)) is False


def test_the_window_does_not_shift_under_daylight_saving():
    """Aurora prices Tariff 93 on AEST year-round, so the window stays put in summer.

    Verified against Aurora's own billed split for January 2026: peak kWh land on local
    (AEDT) hours 8-10 and 17-21, which is exactly 7-9 and 16-20 in fixed AEST. A DST-aware
    window would put them an hour early and misprice roughly 10% of summer hours.
    """
    # 2027-01-05 is a Tuesday. 20:00Z is 07:00 AEDT but only 06:00 AEST -> NOT peak.
    assert PEAK_WINDOW.contains(datetime(2027, 1, 4, 20, 0, tzinfo=UTC)) is False
    # 21:00Z is 08:00 AEDT = 07:00 AEST -> peak, same UTC hour as in winter.
    assert PEAK_WINDOW.contains(datetime(2027, 1, 4, 21, 0, tzinfo=UTC)) is True


def test_peak_window_occupies_the_same_utc_hours_all_year():
    winter = {h for h in range(24) if PEAK_WINDOW.contains(datetime(2026, 6, 3, h, tzinfo=UTC))}
    summer = {h for h in range(24) if PEAK_WINDOW.contains(datetime(2026, 1, 7, h, tzinfo=UTC))}
    assert winter == summer == {6, 7, 8, 9, 10, 21, 22, 23}


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
