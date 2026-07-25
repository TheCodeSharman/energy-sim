"""CostCalculatorService: grid intervals + tariff -> CostBreakdown.

Uses the real Tariff and real Site/GridConnection (no mocks). Rates are Aurora Tariff 93
FY2025-26: peak 31.948, off-peak 14.876, FiT 8.782 c/kWh; June 2026 supply is 0 (unknown).
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from energy_sim.application.cost_calculator import CostCalculatorService
from energy_sim.domain.energy import EnergyQuantity
from energy_sim.domain.grid_connection import GridConnection
from energy_sim.domain.money import Money
from energy_sim.domain.reading import IntervalReading
from energy_sim.domain.site import Site
from energy_sim.domain.tariff import PeakWindow, Tariff, TariffPeriod

UTC = timezone.utc

PEAK_WINDOW = PeakWindow(utc_weekdays=frozenset({1, 2, 3, 4, 5}),
                         utc_hours=frozenset({6, 7, 8, 9, 10, 21, 22, 23}))
FY2025 = TariffPeriod(valid_from=date(2025, 7, 1), peak_c_kwh=Decimal("31.948"),
                      offpeak_c_kwh=Decimal("14.876"), export_c_kwh=Decimal("8.782"),
                      supply_c_day=Decimal("0.0"))
TARIFF = Tariff(periods=[FY2025], peak_window=PEAK_WINDOW)

# 2026-06-01 is a Monday.
PEAK_HOUR = datetime(2026, 6, 1, 6, 0, tzinfo=UTC)     # inside [6,11)
OFFPEAK_HOUR = datetime(2026, 6, 1, 5, 0, tzinfo=UTC)  # outside peak
MIDDAY = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)       # off-peak, export


def _imp(ts, kwh):
    return IntervalReading(ts_utc=ts, interval_s=3600, energy=EnergyQuantity.of(kwh))


def _site():
    grid = GridConnection(name="Aurora meter")
    grid.add_import(_imp(PEAK_HOUR, 2.0))
    grid.add_import(_imp(OFFPEAK_HOUR, 1.0))
    grid.add_export(_imp(MIDDAY, 3.0))
    return Site(name="Home", grid=grid)


def test_import_cost_is_kwh_times_time_of_use_rate():
    breakdown = CostCalculatorService().calculate(_site(), TARIFF)
    # 2.0 x 31.948 (peak) + 1.0 x 14.876 (offpeak) = 78.772 c
    assert breakdown.import_cost == Money.from_cents(Decimal("78.772"))


def test_export_credit_is_kwh_times_fit():
    breakdown = CostCalculatorService().calculate(_site(), TARIFF)
    assert breakdown.export_credit == Money.from_cents(Decimal("26.346"))  # 3.0 x 8.782


def test_net_usage_cost():
    breakdown = CostCalculatorService().calculate(_site(), TARIFF)
    # supply is 0 for June 2026 -> net == usage == 78.772 - 26.346 = 52.426 c
    assert breakdown.net_cost == Money.from_cents(Decimal("52.426"))


def test_peak_offpeak_import_split():
    breakdown = CostCalculatorService().calculate(_site(), TARIFF)
    assert breakdown.peak_import_kwh == 2.0
    assert breakdown.offpeak_import_kwh == 1.0
