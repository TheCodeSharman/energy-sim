"""Export a period from VictoriaMetrics into snapshot rows.

Three sources, three cadences:
  * Power flows (`pf:*_w`) — averaged W over each interval, converted to per-interval kWh, so
    resolution is just the query step.
  * Aurora billed kWh — HOURLY, split by tariff leg; attached where the hour-stamp lines up
    with a row (blank elsewhere).
  * Aurora billed dollars — DAILY only (Aurora records no hourly dollars). Fetched as RAW
    samples so each day contributes exactly one value, and attached to a single row. Querying
    these through query_range would smear each daily value across all 24 hours (staleness
    fill), which a monthly sum would then over-count.

The series->rows merge (`assemble_rows`) is pure and unit-tested; only ``fetch_rows`` does IO.
"""
from __future__ import annotations

import bisect
from datetime import datetime, timedelta

from energy_sim.domain.energy import EnergyQuantity
from energy_sim.infrastructure.csv_store import SnapshotRow
from energy_sim.infrastructure.victoriametrics import VictoriaMetricsClient

# Power flows: average W over each interval (converted to kWh on assembly).
POWER_QUERIES = {
    "import": "avg_over_time(pf:grid_import_w[{step}s])",
    "export": "avg_over_time(pf:grid_export_w[{step}s])",
    "solar": "avg_over_time(pf:solar_w[{step}s])",
    "consumption": "avg_over_time(pf:consumption_w[{step}s])",
}

# Aurora billed kWh: hourly, queried at 1h regardless of --step.
_AURORA_KWH = 'last_over_time(homeassistant_sensor_energy_kwh{{entity="{entity}"}}[1h])'
AURORA_KWH_QUERIES = {
    "peak": _AURORA_KWH.format(entity="sensor.aurora_hourly_kwh_t93_peak"),
    "offpeak": _AURORA_KWH.format(entity="sensor.aurora_hourly_kwh_t93_offpeak"),
    "export": _AURORA_KWH.format(entity="sensor.aurora_hourly_kwh_t140"),
}

# Aurora billed dollars: daily, fetched raw. "other" is the fixed daily supply charge;
# "total" is the all-in billed figure — the end-to-end target.
_AURORA_DOLLAR = 'homeassistant_sensor_state{{entity="{entity}"}}'
AURORA_DOLLAR_SELECTORS = {
    "peak": _AURORA_DOLLAR.format(entity="sensor.aurora_daily_dollar_t93_peak"),
    "offpeak": _AURORA_DOLLAR.format(entity="sensor.aurora_daily_dollar_t93_offpeak"),
    "export": _AURORA_DOLLAR.format(entity="sensor.aurora_daily_dollar_t140"),
    "supply": _AURORA_DOLLAR.format(entity="sensor.aurora_daily_dollar_other"),
    "total": _AURORA_DOLLAR.format(entity="sensor.aurora_daily_dollar_total"),
}

Series = dict[str, list[tuple[datetime, float]]]


def assemble_rows(
    power: Series,
    aurora_kwh: Series,
    aurora_dollars: Series,
    step_seconds: int,
) -> list[SnapshotRow]:
    p = {name: dict(series) for name, series in power.items()}
    kwh = {name: dict(series) for name, series in aurora_kwh.items()}

    def kwh_from_watts(name: str, ts: datetime) -> float | None:
        series = p.get(name, {})
        if not series:
            return None  # series absent entirely (e.g. solar not queried)
        watts = series.get(ts, 0.0)  # gap within a present series -> zero
        return EnergyQuantity.from_average_watts(watts, step_seconds).kwh

    row_timestamps = sorted(set(p.get("import", {})) | set(p.get("export", {}))
                            | set(p.get("solar", {})) | set(p.get("consumption", {})))
    dollars = _dollars_by_row(aurora_dollars, row_timestamps)

    rows = []
    for ts in row_timestamps:
        d = dollars.get(ts, {})
        rows.append(SnapshotRow(
            ts_utc=ts,
            interval_s=step_seconds,
            grid_import_kwh=kwh_from_watts("import", ts) or 0.0,
            grid_export_kwh=kwh_from_watts("export", ts) or 0.0,
            solar_kwh=kwh_from_watts("solar", ts),
            consumption_kwh=kwh_from_watts("consumption", ts),
            aurora_kwh_peak=kwh.get("peak", {}).get(ts),
            aurora_kwh_offpeak=kwh.get("offpeak", {}).get(ts),
            aurora_kwh_export=kwh.get("export", {}).get(ts),
            aurora_dollar_peak=d.get("peak"),
            aurora_dollar_offpeak=d.get("offpeak"),
            aurora_dollar_export=d.get("export"),
            aurora_dollar_supply=d.get("supply"),
            aurora_dollar_total=d.get("total"),
        ))
    return rows


def _dollars_by_row(
    aurora_dollars: Series, row_timestamps: list[datetime]
) -> dict[datetime, dict[str, float]]:
    """Place each daily dollar sample on exactly one row, without losing any.

    A sample lands on the first row at or after its own timestamp (usually an exact hit, since
    both sit on hour marks), or on the last row if it falls past the end of the period. Samples
    colliding on one row accumulate, so the column always sums to the billed period total.
    """
    placed: dict[datetime, dict[str, float]] = {}
    if not row_timestamps:
        return placed
    for leg, samples in aurora_dollars.items():
        for ts, value in samples:
            index = bisect.bisect_left(row_timestamps, ts)
            row_ts = row_timestamps[min(index, len(row_timestamps) - 1)]
            row = placed.setdefault(row_ts, {})
            row[leg] = row.get(leg, 0.0) + value
    return placed


def fetch_rows(
    client: VictoriaMetricsClient, start: datetime, end: datetime, step_seconds: int
) -> list[SnapshotRow]:
    """Rows for the period [start, end). VM's own bounds are inclusive, so ``end`` is pulled
    back a second — otherwise consecutive months would share their boundary sample."""
    last = end - timedelta(seconds=1)
    power = {
        name: client.query_range(q.format(step=step_seconds), start, last, step_seconds)
        for name, q in POWER_QUERIES.items()
    }
    aurora_kwh = {
        name: client.query_range(q, start, last, 3600)
        for name, q in AURORA_KWH_QUERIES.items()
    }
    aurora_dollars = {
        name: client.export(selector, start, last)
        for name, selector in AURORA_DOLLAR_SELECTORS.items()
    }
    return assemble_rows(power, aurora_kwh, aurora_dollars, step_seconds)
