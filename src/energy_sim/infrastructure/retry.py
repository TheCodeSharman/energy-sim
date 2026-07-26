"""Retry transient IO, and never turn a failure into a quieter, smaller answer.

A read that fails is not a read that returned nothing. A transient export error once turned a
32-month sweep into 29 months and $2,302 into $1,817 while still printing a confident total —
the failure was absorbed, the result shrank, and nothing said so. So the rule here is:

  * transient (connection refused, timeout, HTTP 5xx) -> retry with exponential backoff
  * permanent (HTTP 4xx, a TypeError in our own code) -> raise immediately; retrying a bad
    query just wastes the backoff and fails anyway
  * out of attempts -> raise ``Unavailable``; never return a partial or empty result

``sleep`` is injected so the policy can be tested without real waiting.
"""
from __future__ import annotations

import time
import urllib.error
from typing import Callable, TypeVar

T = TypeVar("T")

DEFAULT_ATTEMPTS = 5
DEFAULT_BASE_WAIT = 1.0
DEFAULT_MAX_WAIT = 30.0
DEFAULT_TIMEOUT_S = 60.0


class Unavailable(Exception):
    """A transient operation still failed after exhausting its retries."""


def is_transient(error: BaseException) -> bool:
    """True if retrying could plausibly succeed.

    ``HTTPError`` is a subclass of ``URLError``, so it is checked first: a 400 from a malformed
    query is permanent, a 503 from a busy server is not.
    """
    if isinstance(error, urllib.error.HTTPError):
        return error.code >= 500
    return isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError, OSError))


def with_retry(
    operation: Callable[[], T],
    *,
    describe: str,
    attempts: int = DEFAULT_ATTEMPTS,
    base_wait: float = DEFAULT_BASE_WAIT,
    max_wait: float = DEFAULT_MAX_WAIT,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] | None = None,
) -> T:
    """Run ``operation``, retrying transient failures, and raise rather than degrade."""
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            if not is_transient(error):
                raise
            last = error
            if attempt == attempts:
                break
            wait = min(max_wait, base_wait * 2 ** (attempt - 1))
            if log:
                log(f"{describe} failed ({error}); retrying in {wait:.0f}s "
                    f"(attempt {attempt}/{attempts})")
            sleep(wait)
    raise Unavailable(f"{describe} failed after {attempts} attempts: {last}") from last
