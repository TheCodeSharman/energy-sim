"""Parsing VictoriaMetrics query_range and export responses (pure, no network)."""
from datetime import datetime, timezone

import pytest

from energy_sim.infrastructure.victoriametrics import (
    parse_export_samples,
    parse_query_range_series,
)

UTC = timezone.utc


def test_parses_single_series_into_timestamped_floats():
    payload = {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {"metric": {"__name__": "pf:grid_import_w"},
                 "values": [[1717200000, "123.4"], [1717203600, "130.0"]]},
            ],
        },
    }
    series = parse_query_range_series(payload)
    assert series == [
        (datetime(2024, 6, 1, 0, 0, tzinfo=UTC), 123.4),
        (datetime(2024, 6, 1, 1, 0, tzinfo=UTC), 130.0),
    ]


def test_empty_result_is_empty_series():
    payload = {"status": "success", "data": {"resultType": "matrix", "result": []}}
    assert parse_query_range_series(payload) == []


def test_non_success_status_raises():
    payload = {"status": "error", "error": "bad query"}
    with pytest.raises(ValueError):
        parse_query_range_series(payload)


# --- /api/v1/export (raw samples, JSON-lines, millisecond timestamps) ----------

def test_export_yields_raw_samples_at_their_own_timestamps():
    body = (
        '{"metric":{"__name__":"homeassistant_sensor_state",'
        '"entity":"sensor.aurora_daily_dollar_total"},'
        '"values":[7.3171749798,6.5113325894],'
        '"timestamps":[1780322400000,1780408800000]}\n'
    )
    assert parse_export_samples(body) == [
        (datetime(2026, 6, 1, 14, 0, tzinfo=UTC), 7.3171749798),
        (datetime(2026, 6, 2, 14, 0, tzinfo=UTC), 6.5113325894),
    ]


def test_export_merges_multiple_blocks_in_timestamp_order():
    body = (
        '{"metric":{},"values":[2.0],"timestamps":[1780408800000]}\n'
        '{"metric":{},"values":[1.0],"timestamps":[1780322400000]}\n'
    )
    assert [v for _, v in parse_export_samples(body)] == [1.0, 2.0]


def test_export_of_absent_series_is_empty():
    assert parse_export_samples("") == []
