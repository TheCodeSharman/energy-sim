"""A --month is a LOCAL billing month, not a UTC one.

Aurora stamps each billed day at local midnight (14:00Z in AEST winter), so a UTC month window
drops the month's first billed day and picks up the next month's first — a whole day of error
in the monthly dollar total, at whichever supply rate that day happens to fall under.
"""
from datetime import datetime, timezone

from energy_sim.interface.cli import month_bounds

UTC = timezone.utc


def test_winter_month_starts_at_local_midnight_aest():
    start, end = month_bounds("2026-06")
    assert start == datetime(2026, 5, 31, 14, 0, tzinfo=UTC)   # 2026-06-01 00:00 AEST (UTC+10)
    assert end == datetime(2026, 6, 30, 14, 0, tzinfo=UTC)     # 2026-07-01 00:00 AEST, exclusive


def test_summer_month_follows_daylight_saving_aedt():
    start, end = month_bounds("2027-01")
    assert start == datetime(2026, 12, 31, 13, 0, tzinfo=UTC)  # 2027-01-01 00:00 AEDT (UTC+11)
    assert end == datetime(2027, 1, 31, 13, 0, tzinfo=UTC)


def test_december_rolls_over_the_year():
    start, end = month_bounds("2026-12")
    assert start == datetime(2026, 11, 30, 13, 0, tzinfo=UTC)
    assert end == datetime(2026, 12, 31, 13, 0, tzinfo=UTC)


def test_window_spans_exactly_the_month_length():
    start, end = month_bounds("2026-06")
    assert (end - start).days == 30
