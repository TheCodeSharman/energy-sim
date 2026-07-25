"""VictoriaMetrics read client for /api/v1/query_range and /api/v1/export (stdlib urllib).

Mirrors the write-side pattern in HomeAssistantConfig/scripts/*_import.py (plain urllib,
host http://192.168.88.152:8428), but reads. The JSON parsing is pure so it can be
unit-tested without a network; only the client methods touch IO.

Two read paths, because the two Aurora cadences need different things:
  * ``query_range`` — resampled onto a fixed step. Right for power flows and hourly series.
  * ``export`` — the RAW samples at their own timestamps. Required for Aurora's DAILY dollars:
    query_range at step<1d carries each daily value forward across every hour of the day
    (staleness fill), so summing a month of it over-counts ~24x. Raw export gives exactly one
    sample per day, which is what a monthly total needs.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DEFAULT_VM_URL = "http://192.168.88.152:8428"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_query_range_series(payload: dict) -> list[tuple[datetime, float]]:
    """Flatten a matrix query_range response's first series into (utc_datetime, value).

    Our queries reduce to a single series (sum(...)/pf:*); extra series are ignored.
    """
    if payload.get("status") != "success":
        raise ValueError(f"VictoriaMetrics query failed: {payload.get('error', payload)}")
    result = payload["data"]["result"]
    if not result:
        return []
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


class VictoriaMetricsClient:
    def __init__(self, base_url: str = DEFAULT_VM_URL) -> None:
        self.base_url = base_url.rstrip("/")

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
        with urllib.request.urlopen(url) as resp:
            payload = json.loads(resp.read())
        return parse_query_range_series(payload)

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
        with urllib.request.urlopen(url) as resp:
            return parse_export_samples(resp.read().decode())
