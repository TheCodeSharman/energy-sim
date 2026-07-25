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
