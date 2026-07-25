"""Scaling a Site's grid flows by CT-calibration factors."""
from datetime import datetime, timezone

from energy_sim.application.calibration import calibrate, calibration_factors
from energy_sim.domain.energy import EnergyQuantity
from energy_sim.domain.grid_connection import GridConnection
from energy_sim.domain.reading import IntervalReading
from energy_sim.domain.site import Site
from energy_sim.infrastructure.csv_store import Snapshot, SnapshotRow

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 5, 0, tzinfo=UTC)


def _site(import_kwh: float, export_kwh: float) -> Site:
    grid = GridConnection(name="Aurora meter")
    grid.add_import(IntervalReading(ts_utc=T0, interval_s=3600, energy=EnergyQuantity.of(import_kwh)))
    grid.add_export(IntervalReading(ts_utc=T0, interval_s=3600, energy=EnergyQuantity.of(export_kwh)))
    return Site(name="Home", grid=grid)


def test_calibrate_scales_import_and_export_independently():
    calibrated = calibrate(_site(10.0, 4.0), import_factor=1.1, export_factor=0.5)
    interval = calibrated.grid.intervals()[0]
    assert interval.import_energy.kwh == 11.0
    assert interval.export_energy.kwh == 2.0


def test_calibrate_leaves_the_original_site_untouched():
    original = _site(10.0, 4.0)
    calibrate(original, import_factor=1.1, export_factor=1.1)
    assert original.grid.intervals()[0].import_energy.kwh == 10.0


def test_factors_are_aurora_metered_kwh_over_pf_kwh():
    snapshot = Snapshot([
        SnapshotRow(ts_utc=T0, interval_s=3600, grid_import_kwh=90.0, grid_export_kwh=50.0,
                    solar_kwh=None, consumption_kwh=None,
                    aurora_kwh_peak=40.0, aurora_kwh_offpeak=60.0, aurora_kwh_export=55.0,
                    aurora_dollar_peak=None, aurora_dollar_offpeak=None, aurora_dollar_export=None),
    ])
    factors = calibration_factors(snapshot)
    assert factors.import_factor == 100.0 / 90.0   # CTs read low -> factor > 1
    assert factors.export_factor == 55.0 / 50.0


def test_factors_default_to_unity_when_there_is_nothing_to_calibrate_against():
    snapshot = Snapshot([
        SnapshotRow(ts_utc=T0, interval_s=3600, grid_import_kwh=0.0, grid_export_kwh=0.0,
                    solar_kwh=None, consumption_kwh=None,
                    aurora_kwh_peak=None, aurora_kwh_offpeak=None, aurora_kwh_export=None,
                    aurora_dollar_peak=None, aurora_dollar_offpeak=None, aurora_dollar_export=None),
    ])
    factors = calibration_factors(snapshot)
    assert factors.import_factor == 1.0
    assert factors.export_factor == 1.0
