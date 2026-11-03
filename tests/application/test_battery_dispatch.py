"""SelfConsumptionDispatch: a Battery transforms a Site's grid flows, re-costed unchanged.

Self-consumption policy: store surplus that would otherwise export, spend it to cover import.
The output is a new Site whose GridConnection carries the battery-adjusted import/export, so the
existing CostCalculatorService re-runs over it with no changes — the R2 seam.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from energy_sim.application.battery_dispatch import SelfConsumptionDispatch
from energy_sim.application.cost_calculator import CostCalculatorService
from energy_sim.domain.battery import Battery
from energy_sim.domain.energy import EnergyQuantity
from energy_sim.domain.grid_connection import GridConnection
from energy_sim.domain.reading import IntervalReading
from energy_sim.domain.site import Site
from energy_sim.domain.tariff import PeakWindow, Tariff, TariffPeriod

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 6, 1, 1, 0, tzinfo=UTC)


def _r(ts, kwh):
    return IntervalReading(ts_utc=ts, interval_s=3600, energy=EnergyQuantity.of(kwh))


def _site(imports=(), exports=()):
    grid = GridConnection(name="Aurora meter")
    for ts, k in imports:
        grid.add_import(_r(ts, k))
    for ts, k in exports:
        grid.add_export(_r(ts, k))
    return Site(name="Home", grid=grid)


def _by_ts(site):
    return {gi.ts_utc: gi for gi in site.grid.intervals()}


def _battery(usable=10.0, power=5.0, rt=1.0, soc=0.0):
    return Battery("B", usable_kwh=usable, max_power_kw=power,
                   round_trip_efficiency=rt, initial_soc_kwh=soc)


def test_surplus_is_stored_and_later_deficit_served_from_the_store():
    site = _site(imports=[(T1, 2.0)], exports=[(T0, 3.0)])
    out = SelfConsumptionDispatch().apply(site, _battery())
    adj = _by_ts(out)
    assert adj[T0].export_energy.kwh == 0.0  # 3 kWh surplus charged instead of exported
    assert adj[T1].import_energy.kwh == 0.0  # 2 kWh deficit met from the battery


def test_charge_power_limit_leaves_residual_export():
    site = _site(exports=[(T0, 8.0)])
    out = SelfConsumptionDispatch().apply(site, _battery(power=5.0))  # 5 kWh/h max
    assert _by_ts(out)[T0].export_energy.kwh == 3.0


def test_discharge_limited_by_stored_energy_leaves_residual_import():
    site = _site(imports=[(T1, 4.0)], exports=[(T0, 1.0)])  # only 1 kWh stored
    out = SelfConsumptionDispatch().apply(site, _battery())
    assert _by_ts(out)[T1].import_energy.kwh == 3.0


def test_original_site_is_not_mutated():
    site = _site(exports=[(T0, 3.0)])
    SelfConsumptionDispatch().apply(site, _battery())
    assert _by_ts(site)[T0].export_energy.kwh == 3.0  # input untouched


# --- end-to-end: the battery cuts the bill, re-costed by the SAME service -----

PEAK_WINDOW = PeakWindow(timezone=ZoneInfo("Australia/Hobart"),
                         local_weekdays=frozenset({1, 2, 3, 4, 5}),
                         local_hours=frozenset({7, 8, 9, 16, 17, 18, 19, 20}))
TARIFF = Tariff(periods=[TariffPeriod(valid_from=date(2025, 7, 1), peak_c_kwh=Decimal("35.0"),
                                      offpeak_c_kwh=Decimal("20.0"), export_c_kwh=Decimal("8.0"),
                                      supply_c_day=Decimal("0.0"))],
                peak_window=PEAK_WINDOW)


def test_battery_reduces_net_cost_vs_baseline():
    # Midnight export @ 8c FiT, 1am off-peak import @ 20c. Shifting 3 kWh of export into 2 kWh
    # of avoided import is worth 2*20 - 3*8 saved... net: baseline = 2*20 - 3*8 = 16c;
    # with battery both legs vanish -> 0c. Saving 16c.
    site = _site(imports=[(T1, 2.0)], exports=[(T0, 3.0)])
    baseline = CostCalculatorService().calculate(site, TARIFF)
    with_batt = CostCalculatorService().calculate(
        SelfConsumptionDispatch().apply(site, _battery()), TARIFF)
    assert with_batt.net_cost.cents < baseline.net_cost.cents
