"""EVCostService: the EV's actual cost on the bill, from the Zappi's measured split.

Grid-charged kWh cost the time-of-use import rate; solar-charged kWh cost the forgone export
credit (the FiT you gave up by putting that surplus in the car instead of selling it). Mirrors
CostCalculatorService in shape and reuses the same Tariff.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from energy_sim.application.ev_cost import EVCostService
from energy_sim.domain.ev_charger import EVCharger, EVChargeInterval
from energy_sim.domain.money import Money
from energy_sim.domain.tariff import PeakWindow, Tariff, TariffPeriod

UTC = timezone.utc
PEAK_WINDOW = PeakWindow(timezone=ZoneInfo("Australia/Hobart"),
                         local_weekdays=frozenset({1, 2, 3, 4, 5}),
                         local_hours=frozenset({7, 8, 9, 16, 17, 18, 19, 20}))
TARIFF = Tariff(periods=[TariffPeriod(valid_from=date(2025, 7, 1), peak_c_kwh=Decimal("35.0"),
                                      offpeak_c_kwh=Decimal("20.0"), export_c_kwh=Decimal("8.0"),
                                      supply_c_day=Decimal("0.0"))],
                peak_window=PEAK_WINDOW)

# 2026-06-01 is a Monday. 06:00Z = 16:00 AEST (peak); 05:00Z = 15:00 (off-peak); 12:00Z midday.
PEAK = datetime(2026, 6, 1, 6, 0, tzinfo=UTC)
OFFPEAK = datetime(2026, 6, 1, 5, 0, tzinfo=UTC)
MIDDAY = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _ci(ts, solar, grid):
    return EVChargeInterval(ts_utc=ts, interval_s=3600, solar_kwh=solar, grid_kwh=grid)


def _ev(*intervals):
    ev = EVCharger(name="Zappi")
    for c in intervals:
        ev.add_charge(c)
    return ev


def test_grid_charging_costs_the_time_of_use_import_rate():
    ev = _ev(_ci(PEAK, 0.0, 2.0), _ci(OFFPEAK, 0.0, 1.0))
    breakdown = EVCostService().calculate(ev, TARIFF)
    # 2.0 x 35.0 (peak) + 1.0 x 20.0 (offpeak) = 90.0 c
    assert breakdown.grid_cost == Money.from_cents(Decimal("90.0"))


def test_solar_charging_costs_the_forgone_export_credit():
    ev = _ev(_ci(MIDDAY, 3.0, 0.0))
    breakdown = EVCostService().calculate(ev, TARIFF)
    assert breakdown.forgone_export_credit == Money.from_cents(Decimal("24.0"))  # 3.0 x 8.0


def test_total_is_grid_cost_plus_forgone_credit():
    ev = _ev(_ci(PEAK, 0.0, 2.0), _ci(MIDDAY, 3.0, 0.0))
    breakdown = EVCostService().calculate(ev, TARIFF)
    assert breakdown.total == Money.from_cents(Decimal("94.0"))  # 70.0 grid + 24.0 forgone
