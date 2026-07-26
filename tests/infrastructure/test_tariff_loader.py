"""Loading the real config/tariffs.toml into a Tariff (parsing + wiring)."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from energy_sim.infrastructure.tariff_loader import load_tariff

UTC = timezone.utc
CONFIG = Path(__file__).resolve().parents[2] / "config" / "tariffs.toml"


def test_loads_fy2025_peak_rate():
    # The as-billed rate recovered from Aurora, not the (ex-GST or stale) doc value 31.948.
    tariff = load_tariff(CONFIG)
    assert tariff.import_rate(datetime(2026, 6, 1, 6, 0, tzinfo=UTC)) == Decimal("35.4782")


def test_loads_fy2026_supply_charge():
    tariff = load_tariff(CONFIG)
    assert tariff.supply_charge_per_day(datetime(2026, 7, 15, tzinfo=UTC)) == Decimal("172.3469")


def test_peak_window_parsed_from_config():
    tariff = load_tariff(CONFIG)
    # Saturday is never peak; Monday 06:00 UTC is.
    assert tariff.is_peak(datetime(2026, 6, 6, 6, 0, tzinfo=UTC)) is False
    assert tariff.is_peak(datetime(2026, 6, 1, 6, 0, tzinfo=UTC)) is True


def test_peak_window_is_fixed_aest_not_dst_aware():
    # Aurora prices the ToU window on AEST year-round; a summer timestamp discriminates.
    tariff = load_tariff(CONFIG)
    assert tariff.is_peak(datetime(2026, 1, 6, 21, 0, tzinfo=UTC)) is True   # 07:00 AEST
    assert tariff.is_peak(datetime(2026, 1, 6, 20, 0, tzinfo=UTC)) is False  # 06:00 AEST


def test_billing_days_are_dst_aware_even_though_the_window_is_not():
    tariff = load_tariff(CONFIG)
    assert tariff.billing_timezone.key == "Australia/Hobart"


def test_period_boundary_falls_on_the_local_financial_year_not_the_utc_date():
    """FY periods start 1 July *local*, so the 10 hours from 30 June 14:00Z are already FY N+1.

    Looking the period up on the UTC date prices them in the outgoing year. Small in dollars,
    but it is the same class of error as billing supply on UTC dates.
    """
    tariff = load_tariff(CONFIG)
    just_before = datetime(2026, 6, 30, 13, 59, tzinfo=UTC)   # 2026-06-30 23:59 AEST
    just_after = datetime(2026, 6, 30, 14, 0, tzinfo=UTC)     # 2026-07-01 00:00 AEST
    assert tariff.supply_charge_per_day(just_before) == Decimal("151.1814")
    assert tariff.supply_charge_per_day(just_after) == Decimal("172.3469")
