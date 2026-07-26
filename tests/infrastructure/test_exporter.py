"""Merging VM series into snapshot rows (pure; W-average -> kWh, Aurora on its own stamps).

Two timestamp conventions meet here and they are NOT the same:

  * `avg_over_time(pf:*[Ns])` evaluated at t is the mean over (t-N, t] — the window ENDING at
    t. Its energy therefore belongs to the interval STARTING at t-N.
  * Aurora's hourly kWh are stamped at the hour they cover, i.e. the interval START.

Rows are keyed by interval start, so power samples are shifted back one step and Aurora's are
taken as-is. Getting this wrong charges energy at the neighbouring hour's tariff.

Aurora's dollars are DAILY, so each must land on exactly ONE row or a monthly sum over the CSV
would over-count it.
"""
from datetime import datetime, timedelta, timezone

from energy_sim.infrastructure.exporter import assemble_rows, fetch_rows
from energy_sim.infrastructure.csv_store import SnapshotRow

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 5, 0, tzinfo=UTC)
T1 = datetime(2026, 6, 1, 6, 0, tzinfo=UTC)
T2 = datetime(2026, 6, 1, 7, 0, tzinfo=UTC)


def test_power_sample_is_energy_of_the_interval_it_covers_not_of_its_stamp():
    # 2000 W averaged over the hour ENDING 06:00Z is 2 kWh for the hour STARTING 05:00Z.
    rows = assemble_rows({"import": [(T1, 2000.0)]}, {}, {}, step_seconds=3600)
    assert [r.ts_utc for r in rows] == [T0]
    assert rows[0].grid_import_kwh == 2.0


def test_shift_back_uses_the_actual_step_not_a_fixed_hour():
    five_min = datetime(2026, 6, 1, 5, 5, tzinfo=UTC)
    rows = assemble_rows({"import": [(five_min, 1200.0)]}, {}, {}, step_seconds=300)
    assert [r.ts_utc for r in rows] == [T0]
    assert rows[0].grid_import_kwh == 0.1  # 1200 W for 5 min


def test_hourly_aurora_kwh_attaches_to_the_interval_it_covers():
    power = {
        "import": [(T1, 1000.0), (T2, 2000.0)],   # cover 05:00-06:00 and 06:00-07:00
        "export": [(T2, 500.0)],
        "solar": [(T1, 0.0), (T2, 1500.0)],
        "consumption": [(T1, 1000.0), (T2, 3000.0)],
    }
    aurora_kwh = {"peak": [(T1, 2.0)], "offpeak": [(T0, 1.0)], "export": [(T1, 0.5)]}
    rows = assemble_rows(power, aurora_kwh, {}, step_seconds=3600)
    assert rows == [
        # Export has no sample covering the 05:00 interval, so it is blank rather than 0.0.
        SnapshotRow(ts_utc=T0, interval_s=3600, grid_import_kwh=1.0, grid_export_kwh=None,
                    solar_kwh=0.0, consumption_kwh=1.0,
                    aurora_kwh_peak=None, aurora_kwh_offpeak=1.0, aurora_kwh_export=None,
                    aurora_dollar_peak=None, aurora_dollar_offpeak=None, aurora_dollar_export=None),
        SnapshotRow(ts_utc=T1, interval_s=3600, grid_import_kwh=2.0, grid_export_kwh=0.5,
                    solar_kwh=1.5, consumption_kwh=3.0,
                    aurora_kwh_peak=2.0, aurora_kwh_offpeak=None, aurora_kwh_export=0.5,
                    aurora_dollar_peak=None, aurora_dollar_offpeak=None, aurora_dollar_export=None),
    ]


def test_daily_dollars_land_on_exactly_one_row():
    power = {"import": [(T1, 0.0), (T2, 0.0)]}   # rows start at T0 and T1
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
    power = {"import": [(T1, 0.0), (T2, 0.0)]}   # rows start at T0 and T1
    off_grid_stamp = datetime(2026, 6, 1, 5, 30, tzinfo=UTC)
    rows = assemble_rows(power, {}, {"total": [(off_grid_stamp, 5.0)]}, step_seconds=3600)
    assert [r.aurora_dollar_total for r in rows] == [None, 5.0]


def test_daily_dollar_after_the_last_row_is_not_dropped():
    power = {"import": [(T1, 0.0), (T2, 0.0)]}
    late = datetime(2026, 6, 1, 23, 0, tzinfo=UTC)
    rows = assemble_rows(power, {}, {"total": [(late, 5.0)]}, step_seconds=3600)
    assert sum(r.aurora_dollar_total or 0.0 for r in rows) == 5.0


def test_an_absent_series_is_unknown_not_zero():
    power = {"import": [(T1, 3600000.0)], "export": [], "solar": [], "consumption": []}
    rows = assemble_rows(power, {}, {}, step_seconds=3600)
    assert len(rows) == 1
    assert rows[0].grid_import_kwh == 3600.0  # 3.6 MW avg for 1h
    assert rows[0].grid_export_kwh is None
    assert rows[0].solar_kwh is None
    assert rows[0].aurora_kwh_peak is None


def test_a_gap_inside_a_present_series_is_unknown_not_a_confident_zero():
    # Solar covers both intervals, import only the first. The second row is built from partial
    # coverage; recording "0 kWh imported" there would invent a reading nothing measured.
    power = {"import": [(T1, 1000.0)], "solar": [(T1, 0.0), (T2, 500.0)]}
    rows = assemble_rows(power, {}, {}, step_seconds=3600)
    assert [r.ts_utc for r in rows] == [T0, T1]
    assert rows[0].grid_import_kwh == 1.0
    assert rows[1].grid_import_kwh is None
    assert rows[1].solar_kwh == 0.5


class _RecordingClient:
    """A stand-in VM client recording the windows it was asked for; returns nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, datetime, datetime]] = []

    def query_range(self, query, start, end, step_seconds):
        self.calls.append((query, start, end))
        return []

    def export(self, selector, start, end):
        self.calls.append((selector, start, end))
        return []


def _window(client, needle):
    return {(s, e) for q, s, e in client.calls if needle in q}


def test_fetch_asks_for_power_one_step_ahead_so_rows_cover_the_period():
    # Rows are stamped at interval start, and a power sample covers the step BEFORE its stamp,
    # so covering [start, end) means querying (start+step .. end].
    client = _RecordingClient()
    start = datetime(2026, 5, 31, 14, 0, tzinfo=UTC)
    end = datetime(2026, 6, 30, 14, 0, tzinfo=UTC)

    fetch_rows(client, start, end, 3600)

    assert _window(client, "pf:grid_import_w") == {(start + timedelta(hours=1), end)}


def test_fetch_treats_the_period_end_as_exclusive_for_auroras_own_stamps():
    # VictoriaMetrics includes the end boundary; Aurora's stamps are interval starts, so the
    # last one must fall strictly inside the period or it would be counted twice across months.
    client = _RecordingClient()
    start = datetime(2026, 5, 31, 14, 0, tzinfo=UTC)
    end = datetime(2026, 6, 30, 14, 0, tzinfo=UTC)

    fetch_rows(client, start, end, 3600)

    last = end - timedelta(seconds=1)
    assert _window(client, "aurora_hourly_kwh_t93_peak") == {(start, last)}
    assert _window(client, "aurora_daily_dollar_total") == {(start, last)}
