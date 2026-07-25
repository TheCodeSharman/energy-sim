"""Site aggregate root: owns the device topology + tariff, asserts the energy balance."""
from datetime import datetime, timezone

from energy_sim.domain.energy import EnergyQuantity
from energy_sim.domain.grid_connection import GridConnection
from energy_sim.domain.house_load import HouseLoad
from energy_sim.domain.reading import IntervalReading
from energy_sim.domain.site import Site
from energy_sim.domain.solar_inverter import SolarInverter

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)


def _reading(ts, kwh):
    return IntervalReading(ts_utc=ts, interval_s=3600, energy=EnergyQuantity.of(kwh))


def _site_with(consumption, solar, imp, exp):
    grid = GridConnection(name="Aurora meter")
    grid.add_import(_reading(T0, imp))
    grid.add_export(_reading(T0, exp))
    pv = SolarInverter(name="Sungrow")
    pv.add_reading(_reading(T0, solar))
    load = HouseLoad(name="House")
    load.add_reading(_reading(T0, consumption))
    return Site(name="Home", grid=grid, solar=pv, load=load)


def test_site_exposes_grid_connection():
    site = _site_with(consumption=2.0, solar=1.5, imp=1.0, exp=0.5)
    assert site.grid.name == "Aurora meter"


def test_energy_balance_holds_when_identity_satisfied():
    # consumption = solar + import - export  ->  2.0 = 1.5 + 1.0 - 0.5
    site = _site_with(consumption=2.0, solar=1.5, imp=1.0, exp=0.5)
    assert site.energy_balance_errors(tolerance_kwh=0.001) == []


def test_energy_balance_flags_violating_interval():
    # 3.0 != 1.5 + 1.0 - 0.5 (= 2.0): a 1.0 kWh discrepancy is reported.
    site = _site_with(consumption=3.0, solar=1.5, imp=1.0, exp=0.5)
    errors = site.energy_balance_errors(tolerance_kwh=0.001)
    assert len(errors) == 1
    assert errors[0].ts_utc == T0
