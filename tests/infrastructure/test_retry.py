"""Retry policy: transient failures are retried, permanent ones are not, and giving up raises."""
import urllib.error

import pytest

from energy_sim.infrastructure.retry import Unavailable, is_transient, with_retry


class FakeClock:
    """Records the waits a caller asked for instead of actually sleeping."""

    def __init__(self):
        self.waits = []

    def __call__(self, seconds):
        self.waits.append(seconds)


def failing(times, exception, then="ok"):
    """An operation that raises ``exception`` the first ``times`` calls, then returns ``then``."""
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        if calls["n"] <= times:
            raise exception
        return then

    return operation


def test_a_transient_failure_is_retried_until_it_succeeds():
    result = with_retry(failing(2, TimeoutError("slow")), describe="fetch", sleep=FakeClock())
    assert result == "ok"


def test_backoff_grows_between_attempts():
    clock = FakeClock()
    with_retry(failing(3, TimeoutError("slow")), describe="fetch", sleep=clock)
    assert clock.waits == sorted(clock.waits) and clock.waits[0] < clock.waits[-1]


def test_backoff_is_capped():
    clock = FakeClock()
    with pytest.raises(Unavailable):
        with_retry(failing(99, TimeoutError("slow")), describe="fetch",
                   attempts=8, max_wait=5.0, sleep=clock)
    assert max(clock.waits) == 5.0


def test_exhausting_the_attempts_raises_rather_than_returning_a_degraded_result():
    with pytest.raises(Unavailable, match="fetch"):
        with_retry(failing(99, TimeoutError("slow")), describe="fetch",
                   attempts=3, sleep=FakeClock())


def test_the_original_failure_is_kept_as_the_cause():
    original = TimeoutError("slow")
    with pytest.raises(Unavailable) as excinfo:
        with_retry(failing(99, original), describe="fetch", attempts=2, sleep=FakeClock())
    assert excinfo.value.__cause__ is original


def test_a_permanent_failure_is_not_retried():
    clock = FakeClock()
    bad_request = urllib.error.HTTPError("http://vm/api", 400, "Bad Request", {}, None)
    with pytest.raises(urllib.error.HTTPError):
        with_retry(failing(99, bad_request), describe="fetch", sleep=clock)
    assert clock.waits == []


def test_a_server_error_is_transient_but_a_client_error_is_not():
    assert is_transient(urllib.error.HTTPError("u", 503, "busy", {}, None))
    assert not is_transient(urllib.error.HTTPError("u", 404, "gone", {}, None))


def test_connection_and_timeout_failures_are_transient():
    assert is_transient(urllib.error.URLError("connection refused"))
    assert is_transient(TimeoutError("timed out"))


def test_a_programming_error_is_not_transient():
    assert not is_transient(TypeError("wrong argument"))
