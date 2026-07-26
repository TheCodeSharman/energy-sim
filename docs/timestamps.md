# Interval timestamps

Rows are keyed by **interval start**. The two data sources disagree about what a timestamp means,
so one of them has to be shifted on the way in.

## The two conventions

```python
# avg_over_time(pf:grid_import_w[3600s]) evaluated at 06:00Z
#   -> the mean over (05:00Z, 06:00Z]  — the window ENDING at the stamp
# so its energy belongs to the interval STARTING at 05:00Z:
covered = timedelta(seconds=step_seconds)
p = {name: {ts - covered: value for ts, value in series} for name, series in power.items()}
```

- **`pf:*` power flows** — `avg_over_time(x[Ns])` at `t` is the mean over `(t-N, t]`. Shift back
  one step to get the interval it covers. `fetch_rows` also queries a step *forward*
  (`start+step .. end`) so the samples tile `[start, end)`.
- **Aurora hourly kWh** — already stamped at the hour they cover. Use as-is.

Aurora's own peak/off-peak split agrees with the peak-window rule on 710/710 hours of June 2026
under this reading, which is what confirms it.

## The symptom, if you get it wrong

Treating a power stamp as an interval *start* charges its energy at the neighbouring hour's tariff.
The error shrinks as the step shrinks, so it shows up as **a modelled cost that moves when you
change `--step-seconds`**:

| step | peak-share error vs Aurora |
|---|---|
| 3600s | +0.232pp |
| 900s | −0.240pp |
| 300s | −0.523pp |

Correct handling is resolution-independent — 3600s, 900s and 300s agree to the cent. That property
is the cheapest regression test available: if two resolutions disagree, the interval convention is
wrong somewhere.

## See also

- [aurora-data.md](aurora-data.md) — Aurora's own cadences and clocks
- `src/energy_sim/infrastructure/exporter.py`, `tests/infrastructure/test_exporter.py`
