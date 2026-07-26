"""Parsing VictoriaMetrics query_range and export responses (pure, no network)."""
import json
from datetime import datetime, timezone

import pytest

from energy_sim.infrastructure.retry import Unavailable
from energy_sim.infrastructure.victoriametrics import (
    VictoriaMetricsClient,
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


def test_more_than_one_series_raises_rather_than_silently_taking_the_first():
    """Our queries reduce to one series; several means the query is wrong, not that we pick one."""
    payload = {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {"metric": {"instance": "a"}, "values": [[1717200000, "1.0"]]},
                {"metric": {"instance": "b"}, "values": [[1717200000, "2.0"]]},
            ],
        },
    }
    with pytest.raises(ValueError, match="2 series"):
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


# --- the client's IO policy: bounded waits, retries, and no quiet degradation --

ONE_SERIES = json.dumps({
    "status": "success",
    "data": {"resultType": "matrix", "result": [{"metric": {}, "values": [[1717200000, "5.0"]]}]},
})

JUNE = (datetime(2024, 6, 1, tzinfo=UTC), datetime(2024, 7, 1, tzinfo=UTC))


class FakeVM:
    """Stands in for the network: fails a given number of times, then serves a body."""

    def __init__(self, body=ONE_SERIES, failures=0):
        self.body, self.failures = body, failures
        self.timeouts, self.urls = [], []

    def __call__(self, url, timeout):
        self.urls.append(url)
        self.timeouts.append(timeout)
        if self.failures > 0:
            self.failures -= 1
            raise TimeoutError("VictoriaMetrics did not answer")
        return self.body


def _client(vm):
    return VictoriaMetricsClient("http://vm:8428", open_url=vm, sleep=lambda _: None)


def test_every_read_is_given_a_timeout_so_a_hung_server_cannot_hang_the_run():
    vm = FakeVM()
    _client(vm).query_range("up", *JUNE, 3600)
    assert vm.timeouts and all(t > 0 for t in vm.timeouts)


def test_a_transient_read_failure_is_retried_rather_than_losing_the_series():
    vm = FakeVM(failures=2)
    assert _client(vm).query_range("up", *JUNE, 3600) == [
        (datetime(2024, 6, 1, tzinfo=UTC), 5.0)
    ]


def test_a_read_that_never_succeeds_raises_instead_of_returning_an_empty_series():
    vm = FakeVM(failures=99)
    with pytest.raises(Unavailable):
        _client(vm).query_range("up", *JUNE, 3600)


def test_export_retries_and_raises_on_the_same_terms():
    vm = FakeVM(body='{"metric":{},"values":[1.0],"timestamps":[1717200000000]}', failures=2)
    assert _client(vm).export('x{y="z"}', *JUNE) == [(datetime(2024, 6, 1, tzinfo=UTC), 1.0)]

    with pytest.raises(Unavailable):
        _client(FakeVM(failures=99)).export('x{y="z"}', *JUNE)
