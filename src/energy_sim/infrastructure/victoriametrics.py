"""VictoriaMetrics read client for /api/v1/query_range and /api/v1/export (stdlib urllib).

Two read paths: ``query_range`` resamples onto a fixed step, ``export`` returns the RAW
samples. Aurora's daily dollars need ``export`` — see docs/aurora-data.md. Parsing is pure
so it can be unit-tested without a network; only the client methods touch IO.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Callable

from energy_sim.infrastructure.retry import (
    DEFAULT_ATTEMPTS,
    DEFAULT_TIMEOUT_S,
    with_retry,
)

DEFAULT_VM_URL = "http://192.168.88.152:8428"

log = logging.getLogger(__name__)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_query_range_series(payload: dict) -> list[tuple[datetime, float]]:
    """Flatten a matrix query_range response's single series into (utc_datetime, value).

    Every query here reduces to one series (``sum(...)`` / a ``pf:*`` recording rule), so more
    than one means the query did not reduce the way we assume — a stray label, a renamed rule,
    two instances reporting the same metric. Taking ``result[0]`` would answer confidently from
    an arbitrary half of the data, so this raises instead.
    """
    if payload.get("status") != "success":
        raise ValueError(f"VictoriaMetrics query failed: {payload.get('error', payload)}")
    result = payload["data"]["result"]
    if not result:
        return []
    if len(result) > 1:
        labels = [r.get("metric", {}) for r in result]
        raise ValueError(
            f"expected one series, got {len(result)} series: {labels}. "
            "The query does not reduce to a single series; fix the query rather than "
            "picking one of them."
        )
    values = result[0]["values"]
    return [
        (datetime.fromtimestamp(int(ts), tz=timezone.utc), float(val))
        for ts, val in values
    ]


def parse_export_samples(body: str) -> list[tuple[datetime, float]]:
    """Flatten an /api/v1/export JSON-lines body into (utc_datetime, value), time-ordered.

    Each line is one series block with parallel ``timestamps`` (milliseconds) and ``values``.
    Blocks from several series are merged; our selectors match a single entity.
    """
    samples: list[tuple[datetime, float]] = []
    for line in body.splitlines():
        if not line.strip():
            continue
        block = json.loads(line)
        for ts_ms, value in zip(block["timestamps"], block["values"]):
            samples.append(
                (datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc), float(value))
            )
    return sorted(samples)


def _urlopen_text(url: str, timeout: float) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode()


class VictoriaMetricsClient:
    """Reads from VictoriaMetrics, with bounded waits and no quiet degradation.

    Every read is retried on transient failure and raises when it cannot succeed — an
    unreachable VM must stop the run, not silently shrink its answer. ``open_url`` is the
    single IO seam, so the policy is testable without a server.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_VM_URL,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        attempts: int = DEFAULT_ATTEMPTS,
        open_url: Callable[[str, float], str] = _urlopen_text,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.attempts = attempts
        self._open_url = open_url
        self._sleep = sleep

    def _read(self, url: str, describe: str) -> str:
        return with_retry(
            lambda: self._open_url(url, self.timeout_s),
            describe=describe,
            attempts=self.attempts,
            sleep=self._sleep,
            log=log.warning,
        )

    def query_range(
        self, query: str, start: datetime, end: datetime, step_seconds: int
    ) -> list[tuple[datetime, float]]:
        params = urllib.parse.urlencode({
            "query": query,
            "start": _iso(start),
            "end": _iso(end),
            "step": step_seconds,
        })
        url = f"{self.base_url}/api/v1/query_range?{params}"
        body = self._read(url, f"query_range {query} over {_iso(start)}..{_iso(end)}")
        return parse_query_range_series(json.loads(body))

    def export(
        self, selector: str, start: datetime, end: datetime
    ) -> list[tuple[datetime, float]]:
        """Raw samples for a series selector, at their own timestamps (no resampling)."""
        params = urllib.parse.urlencode({
            "match[]": selector,
            "start": _iso(start),
            "end": _iso(end),
        })
        url = f"{self.base_url}/api/v1/export?{params}"
        return parse_export_samples(
            self._read(url, f"export {selector} over {_iso(start)}..{_iso(end)}")
        )
