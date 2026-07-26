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


def _flows(grid_import, grid_export, solar, consumption, ts=T0):
    """A row carrying only the four flow columns — Aurora's are blank."""
    return SnapshotRow(ts_utc=ts, interval_s=3600,
                       grid_import_kwh=grid_import, grid_export_kwh=grid_export,
                       solar_kwh=solar, consumption_kwh=consumption,
                       aurora_kwh_peak=None, aurora_kwh_offpeak=None, aurora_kwh_export=None,
                       aurora_dollar_peak=None, aurora_dollar_offpeak=None,
                       aurora_dollar_export=None)


def test_an_unmeasured_flow_round_trips_as_blank_not_as_zero(tmp_path):
    path = tmp_path / "snap.csv"
    write_snapshot(path, [_flows(None, 0.5, 1.5, 3.0)])
    assert read_snapshot(path).rows[0].grid_import_kwh is None


def test_a_row_missing_one_flow_is_reported_as_incomplete(tmp_path):
    path = tmp_path / "snap.csv"
    write_snapshot(path, [_flows(1.0, 0.0, None, None, ts=T0),
                          _flows(2.0, 0.5, 1.5, 3.0, ts=T1)])
    assert [r.ts_utc for r in read_snapshot(path).incomplete_rows()] == [T0]


def test_a_row_measuring_nothing_at_all_is_not_called_incomplete(tmp_path):
    # Nothing was measured anywhere, so there is no partial coverage to warn about.
    path = tmp_path / "snap.csv"
    write_snapshot(path, [_flows(None, None, None, None)])
    assert read_snapshot(path).incomplete_rows() == []


def test_totals_treat_an_unmeasured_interval_as_no_energy(tmp_path):
    path = tmp_path / "snap.csv"
    write_snapshot(path, [_flows(None, None, 1.5, 3.0, ts=T0),
                          _flows(2.0, 0.5, 1.5, 3.0, ts=T1)])
    snapshot = read_snapshot(path)
    assert snapshot.pf_import_kwh_total() == 2.0
    assert snapshot.pf_export_kwh_total() == 0.5
