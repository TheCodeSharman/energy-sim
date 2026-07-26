# Reading Aurora billed data

How to read Aurora Plus billing out of VictoriaMetrics without silently corrupting it. Aurora is
the ground truth this simulator validates against, and it has three traps.

## Aurora uses two different clocks

Do not assume one timezone covers both.

| what | clock | why it matters |
|---|---|---|
| **billing days** (the fixed daily supply charge) | local calendar days, **DST-aware** | daily records are stamped at local midnight: `13:00Z` in AEDT, `14:00Z` in AEST |
| **time-of-use window** (peak / off-peak) | **fixed AEST (UTC+10)**, never shifts | in UTC the window is always hours `{6,7,8,9,10,21,22,23}` |

```toml
# config/tariffs.toml
[billing]
timezone = "Australia/Hobart"   # calendar days, follows DST

[peak_window]
timezone = "Etc/GMT-10"         # POSIX sign convention: this IS UTC+10, and never shifts
```

Aurora's own billed split is the proof: in January 2026 its peak kWh land on local (AEDT) hours
8–10 and 17–21, which is exactly 7–9 and 16–20 in AEST. Treating the window as DST-aware misprices
roughly 10% of every summer month — and it is **invisible in winter**, when AEST and local time
coincide, so a winter-only check will not catch it.

## Billed dollars are daily; billed kWh are hourly

Aurora records dollars **only** at day granularity. Read them as raw samples:

```
/api/v1/export?match[]=homeassistant_sensor_state{entity="sensor.aurora_daily_dollar_total"}
```

A `query_range` at any sub-day step carries each daily value across all 24 hours (staleness fill),
so summing a month of it over-counts by ~24x. `/api/v1/export` returns exactly one sample per day.
Hourly kWh (`homeassistant_sensor_energy_kwh`) are fine to read with `query_range`.

Note the metric name: query `homeassistant_sensor_state{entity="..."}`, never the bare entity.

## A month is a local billing month, end-exclusive

`month_bounds()` resolves `--month` in the billing timezone, so June 2026 is
`2026-05-31T14:00Z .. 2026-06-30T14:00Z` — 720 rows, exactly 30 billed days.

A naive UTC month window is offset by the UTC offset: it drops the month's first billed day and
gains the next month's first, at whichever supply rate *that* day falls under. The tell is the
supply column no longer being a clean multiple of the daily rate.

VictoriaMetrics treats `start`/`end` as inclusive, so `fetch_rows` pulls `end` back one second;
otherwise consecutive months share a boundary sample.

## See also

- [timestamps.md](timestamps.md) — the interval convention for `pf:*` power flows
- [tariffs.md](tariffs.md) — recovering rates from this data
- `src/energy_sim/infrastructure/exporter.py`, `src/energy_sim/interface/cli.py`
