"""CSV snapshot store: round-trip persistence + hydrating a Site + Aurora aggregates."""
from decimal import Decimal
from datetime import datetime, timezone

from energy_sim.infrastructure.csv_store import SnapshotRow, read_snapshot, write_snapshot

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 5, 0, tzinfo=UTC)  # off-peak
T1 = datetime(2026, 6, 1, 6, 0, tzinfo=UTC)  # peak


def _rows():
    return [
        SnapshotRow(ts_utc=T0, interval_s=3600, grid_import_kwh=1.0, grid_export_kwh=0.0,
                    solar_kwh=0.0, consumption_kwh=1.0,
                    aurora_kwh_peak=0.0, aurora_kwh_offpeak=1.0, aurora_kwh_export=0.0,
                    aurora_dollar_peak=Decimal("0.0"), aurora_dollar_offpeak=Decimal("0.14876"),
                    aurora_dollar_export=Decimal("0.0")),
        SnapshotRow(ts_utc=T1, interval_s=3600, grid_import_kwh=2.0, grid_export_kwh=0.5,
                    solar_kwh=1.5, consumption_kwh=3.0,
                    aurora_kwh_peak=2.0, aurora_kwh_offpeak=0.0, aurora_kwh_export=0.5,
                    aurora_dollar_peak=Decimal("0.63896"), aurora_dollar_offpeak=Decimal("0.0"),
                    aurora_dollar_export=Decimal("-0.04391")),
    ]


def test_round_trip_preserves_rows(tmp_path):
    path = tmp_path / "snap.csv"
    write_snapshot(path, _rows())
    snapshot = read_snapshot(path)
    assert snapshot.rows == _rows()


def test_to_site_populates_grid_solar_and_load(tmp_path):
    path = tmp_path / "snap.csv"
    write_snapshot(path, _rows())
    site = read_snapshot(path).to_site()

    intervals = site.grid.intervals()
    assert [gi.import_energy.kwh for gi in intervals] == [1.0, 2.0]
    assert [gi.export_energy.kwh for gi in intervals] == [0.0, 0.5]
    assert [r.energy.kwh for r in site.solar.readings] == [0.0, 1.5]
    assert [r.energy.kwh for r in site.load.readings] == [1.0, 3.0]


def test_aurora_totals(tmp_path):
    path = tmp_path / "snap.csv"
    write_snapshot(path, _rows())
    snapshot = read_snapshot(path)
    assert snapshot.has_aurora is True
    assert snapshot.aurora_kwh_totals() == (2.0, 1.0, 0.5)  # peak, offpeak, export


def test_aurora_absent_when_columns_blank(tmp_path):
    rows = [SnapshotRow(ts_utc=T0, interval_s=3600, grid_import_kwh=1.0, grid_export_kwh=0.0,
                        solar_kwh=None, consumption_kwh=None,
                        aurora_kwh_peak=None, aurora_kwh_offpeak=None, aurora_kwh_export=None,
                        aurora_dollar_peak=None, aurora_dollar_offpeak=None, aurora_dollar_export=None)]
    path = tmp_path / "snap.csv"
    write_snapshot(path, rows)
    snapshot = read_snapshot(path)
    assert snapshot.has_aurora is False
    # solar/load absent -> Site still builds, with no solar/load devices
    assert snapshot.to_site().solar is None
