"""Merging VM series into snapshot rows (pure; W-average -> kWh, Aurora on its own stamps).

Aurora arrives at two cadences: hourly kWh (per tariff leg) and DAILY dollars. A daily dollar
must land on exactly ONE row, or a monthly sum over the CSV would over-count it.
"""
from datetime import datetime, timedelta, timezone

from energy_sim.infrastructure.exporter import assemble_rows, fetch_rows
from energy_sim.infrastructure.csv_store import SnapshotRow

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 5, 0, tzinfo=UTC)
T1 = datetime(2026, 6, 1, 6, 0, tzinfo=UTC)


def test_assemble_converts_watts_to_kwh_and_aligns_hourly_aurora_kwh():
    power = {
        "import": [(T0, 1000.0), (T1, 2000.0)],
        "export": [(T1, 500.0)],
        "solar": [(T0, 0.0), (T1, 1500.0)],
        "consumption": [(T0, 1000.0), (T1, 3000.0)],
    }
    aurora_kwh = {
        "peak": [(T1, 2.0)],
        "offpeak": [(T0, 1.0)],
        "export": [(T1, 0.5)],
    }
    rows = assemble_rows(power, aurora_kwh, {}, step_seconds=3600)
    assert rows == [
        SnapshotRow(ts_utc=T0, interval_s=3600, grid_import_kwh=1.0, grid_export_kwh=0.0,
                    solar_kwh=0.0, consumption_kwh=1.0,
                    aurora_kwh_peak=None, aurora_kwh_offpeak=1.0, aurora_kwh_export=None,
                    aurora_dollar_peak=None, aurora_dollar_offpeak=None, aurora_dollar_export=None),
        SnapshotRow(ts_utc=T1, interval_s=3600, grid_import_kwh=2.0, grid_export_kwh=0.5,
                    solar_kwh=1.5, consumption_kwh=3.0,
                    aurora_kwh_peak=2.0, aurora_kwh_offpeak=None, aurora_kwh_export=0.5,
                    aurora_dollar_peak=None, aurora_dollar_offpeak=None, aurora_dollar_export=None),
    ]


def test_daily_dollars_land_on_exactly_one_row():
    power = {"import": [(T0, 0.0), (T1, 0.0)]}
    aurora_dollars = {
        "peak": [(T1, 3.319163001)],
        "offpeak": [(T1, 2.5530553448)],
        "export": [(T1, -0.066857366)],
        "supply": [(T1, 1.511814)],
        "total": [(T1, 7.3171749798)],
    }
    rows = assemble_rows(power, {}, aurora_dollars, step_seconds=3600)

    assert [r.aurora_dollar_total for r in rows] == [None, 7.3171749798]
    assert rows[1].aurora_dollar_supply == 1.511814
    assert rows[1].aurora_dollar_peak == 3.319163001
    assert rows[1].aurora_dollar_offpeak == 2.5530553448
    assert rows[1].aurora_dollar_export == -0.066857366


def test_daily_dollar_between_rows_attaches_to_the_next_row():
    off_grid_stamp = datetime(2026, 6, 1, 5, 30, tzinfo=UTC)
    power = {"import": [(T0, 0.0), (T1, 0.0)]}
    rows = assemble_rows(power, {}, {"total": [(off_grid_stamp, 5.0)]}, step_seconds=3600)
    assert [r.aurora_dollar_total for r in rows] == [None, 5.0]


def test_daily_dollar_after_the_last_row_is_not_dropped():
    late = datetime(2026, 6, 1, 23, 0, tzinfo=UTC)
    power = {"import": [(T0, 0.0), (T1, 0.0)]}
    rows = assemble_rows(power, {}, {"total": [(late, 5.0)]}, step_seconds=3600)
    assert sum(r.aurora_dollar_total or 0.0 for r in rows) == 5.0


class _RecordingClient:
    """A stand-in VM client that records the windows it was asked for and returns nothing."""

    def __init__(self) -> None:
        self.windows: list[tuple[datetime, datetime]] = []

    def query_range(self, query, start, end, step_seconds):
        self.windows.append((start, end))
        return []

    def export(self, selector, start, end):
        self.windows.append((start, end))
        return []


def test_fetch_treats_the_period_end_as_exclusive():
    # VictoriaMetrics includes the end boundary, which would double-count the day/hour shared
    # with the next period — so a month boundary must not appear in two snapshots.
    client = _RecordingClient()
    start = datetime(2026, 5, 31, 14, 0, tzinfo=UTC)
    end = datetime(2026, 6, 30, 14, 0, tzinfo=UTC)

    fetch_rows(client, start, end, 3600)

    assert client.windows
    assert set(client.windows) == {(start, end - timedelta(seconds=1))}


def test_missing_grid_series_defaults_to_zero_but_absent_solar_is_none():
    power = {"import": [(T0, 3600000.0)], "export": [], "solar": [], "consumption": []}
    rows = assemble_rows(power, {}, {}, step_seconds=3600)
    assert len(rows) == 1
    assert rows[0].grid_import_kwh == 3600.0  # 3.6 MW avg for 1h
    assert rows[0].grid_export_kwh == 0.0
    assert rows[0].solar_kwh is None
    assert rows[0].aurora_kwh_peak is None
