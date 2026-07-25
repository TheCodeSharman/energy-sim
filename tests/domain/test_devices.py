"""Device topology: single-meter devices and the dual-channel GridConnection."""
from datetime import datetime, timezone

from energy_sim.domain.device import DeviceRole
from energy_sim.domain.energy import EnergyQuantity
from energy_sim.domain.grid_connection import GridConnection, GridInterval
from energy_sim.domain.house_load import HouseLoad
from energy_sim.domain.reading import IntervalReading
from energy_sim.domain.solar_inverter import SolarInverter

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 6, 1, 1, 0, tzinfo=UTC)


def _reading(ts, kwh):
    return IntervalReading(ts_utc=ts, interval_s=3600, energy=EnergyQuantity.of(kwh))


def test_single_meter_device_records_readings_and_role():
    solar = SolarInverter(name="Sungrow")
    solar.add_reading(_reading(T0, 3.0))
    assert solar.role is DeviceRole.SOLAR
    assert [r.energy.kwh for r in solar.readings] == [3.0]


def test_house_load_role():
    assert HouseLoad(name="House").role is DeviceRole.LOAD


def test_grid_connection_pairs_import_and_export_by_timestamp():
    grid = GridConnection(name="Aurora meter")
    grid.add_import(_reading(T0, 1.0))
    grid.add_export(_reading(T0, 0.0))
    grid.add_import(_reading(T1, 0.0))
    grid.add_export(_reading(T1, 0.5))

    intervals = grid.intervals()
    assert intervals == [
        GridInterval(ts_utc=T0, interval_s=3600,
                     import_energy=EnergyQuantity.of(1.0), export_energy=EnergyQuantity.of(0.0)),
        GridInterval(ts_utc=T1, interval_s=3600,
                     import_energy=EnergyQuantity.of(0.0), export_energy=EnergyQuantity.of(0.5)),
    ]


def test_grid_intervals_sorted_even_when_added_out_of_order():
    grid = GridConnection(name="Aurora meter")
    grid.add_import(_reading(T1, 0.2))
    grid.add_import(_reading(T0, 0.1))
    assert [gi.ts_utc for gi in grid.intervals()] == [T0, T1]


def test_grid_missing_channel_reads_as_zero():
    # An import with no matching export reading pairs against zero export.
    grid = GridConnection(name="Aurora meter")
    grid.add_import(_reading(T0, 1.0))
    (only,) = grid.intervals()
    assert only.export_energy == EnergyQuantity.zero()
