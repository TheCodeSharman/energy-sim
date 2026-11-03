"""simulate_grid: derive the grid connection from the two exogenous inputs, solar and load.

Grid is an OUTPUT of the model, not an input — every scenario changes it. Per interval the net
of load minus solar is either drawn from the grid (import) or pushed to it (export). This is the
inverse of the energy identity the Site already checks: consumption = solar + import - export.
"""
from datetime import datetime, timezone

from energy_sim.application.grid_simulation import simulate_grid
from energy_sim.domain.energy import EnergyQuantity
from energy_sim.domain.house_load import HouseLoad
from energy_sim.domain.reading import IntervalReading
from energy_sim.domain.solar_inverter import SolarInverter

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 6, 1, 1, 0, tzinfo=UTC)


def _r(ts, kwh):
    return IntervalReading(ts_utc=ts, interval_s=3600, energy=EnergyQuantity.of(kwh))


def _inputs(solar_kwh, load_kwh, ts=T0):
    solar = SolarInverter(name="Sungrow")
    load = HouseLoad(name="House")
    solar.add_reading(_r(ts, solar_kwh))
    load.add_reading(_r(ts, load_kwh))
    return solar, load


def test_load_exceeding_solar_is_imported():
    grid = simulate_grid(*_inputs(solar_kwh=1.0, load_kwh=3.0))
    (gi,) = grid.intervals()
    assert gi.import_energy.kwh == 2.0
    assert gi.export_energy.kwh == 0.0


def test_solar_exceeding_load_is_exported():
    grid = simulate_grid(*_inputs(solar_kwh=4.0, load_kwh=1.0))
    (gi,) = grid.intervals()
    assert gi.export_energy.kwh == 3.0
    assert gi.import_energy.kwh == 0.0


def test_balanced_interval_touches_the_grid_not_at_all():
    grid = simulate_grid(*_inputs(solar_kwh=2.0, load_kwh=2.0))
    (gi,) = grid.intervals()
    assert gi.import_energy.kwh == 0.0
    assert gi.export_energy.kwh == 0.0


def test_each_interval_is_derived_independently():
    solar = SolarInverter(name="Sungrow")
    load = HouseLoad(name="House")
    solar.add_reading(_r(T0, 1.0)); load.add_reading(_r(T0, 3.0))   # deficit -> import 2
    solar.add_reading(_r(T1, 5.0)); load.add_reading(_r(T1, 1.0))   # surplus -> export 4
    by_ts = {gi.ts_utc: gi for gi in simulate_grid(solar, load).intervals()}
    assert by_ts[T0].import_energy.kwh == 2.0
    assert by_ts[T1].export_energy.kwh == 4.0
