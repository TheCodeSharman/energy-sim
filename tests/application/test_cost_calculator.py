"""CostCalculatorService: grid intervals + tariff -> CostBreakdown.

Uses the real Tariff and real Site/GridConnection (no mocks). Rates are Aurora Tariff 93
FY2025-26: peak 31.948, off-peak 14.876, FiT 8.782 c/kWh; June 2026 supply is 0 (unknown).
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from energy_sim.application.cost_calculator import CostCalculatorService
from energy_sim.domain.energy import EnergyQuantity
from energy_sim.domain.grid_connection import GridConnection
from energy_sim.domain.money import Money
from energy_sim.domain.reading import IntervalReading
from energy_sim.domain.site import Site
from energy_sim.domain.tariff import PeakWindow, Tariff, TariffPeriod

UTC = timezone.utc

PEAK_WINDOW = PeakWindow(timezone=ZoneInfo("Australia/Hobart"),
                         local_weekdays=frozenset({1, 2, 3, 4, 5}),
                         local_hours=frozenset({7, 8, 9, 16, 17, 18, 19, 20}))
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


# --- supply charge is billed per LOCAL day, not per UTC date ------------------

SUPPLY_TARIFF = Tariff(
    periods=[TariffPeriod(valid_from=date(2025, 7, 1), peak_c_kwh=Decimal("35.4782"),
                          offpeak_c_kwh=Decimal("16.6862"), export_c_kwh=Decimal("8.782"),
                          supply_c_day=Decimal("100.0"))],
    peak_window=PEAK_WINDOW,
)


def test_supply_charge_counts_local_billing_days_not_utc_dates():
    """One local day (2026-06-01 Hobart) spans two UTC dates — Aurora bills it once.

    Counting UTC dates overcharges a month by a whole day: a 30-day local billing month
    covers 31 distinct UTC dates.
    """
    grid = GridConnection(name="Aurora meter")
    for hour in range(24):  # 2026-05-31T14:00Z .. 2026-06-01T13:00Z = all of 1 June, Hobart
        grid.add_import(_imp(datetime(2026, 5, 31, 14, 0, tzinfo=UTC) + timedelta(hours=hour), 0.0))
    breakdown = CostCalculatorService().calculate(Site(name="Home", grid=grid), SUPPLY_TARIFF)
    assert breakdown.supply_charge == Money.from_dollars("1.00")


def test_supply_days_follow_the_billing_zone_even_though_the_window_does_not():
    """Aurora uses two different clocks, and the model must too.

    Billing DAYS are local calendar days (its daily records are stamped 13:00Z in AEDT and
    14:00Z in AEST), but the ToU WINDOW is priced on fixed AEST year-round. A summer day
    discriminates: 2026-01-15 Hobart runs 13:00Z-13:00Z, which straddles two UTC+10 dates.
    """
    grid = GridConnection(name="Aurora meter")
    for hour in range(24):  # all of 2026-01-15, Hobart local
        grid.add_import(_imp(datetime(2026, 1, 14, 13, 0, tzinfo=UTC) + timedelta(hours=hour), 0.0))
    tariff = Tariff(
        periods=SUPPLY_TARIFF._periods,
        peak_window=PEAK_WINDOW,
        billing_timezone=ZoneInfo("Australia/Hobart"),
    )
    breakdown = CostCalculatorService().calculate(Site(name="Home", grid=grid), tariff)
    assert breakdown.supply_charge == Money.from_dollars("1.00")
