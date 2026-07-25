# energy-sim — session handover

Continuation notes for HI-61 (energy simulator, iteration 1). Read this + `REQUIREMENTS.md`
(the R1.1 entry is the current state) + the approved plan at
`~/.claude/plans/ok-i-d-like-to-purring-lark.md`.

## Goal (what "done" for iteration 1 means)

Estimate the household electricity **cost in dollars** from real historical grid import/export
and compare it to the **actual Aurora Plus billed dollars**. The **$ end-to-end number is the
target** (user's words); kWh is a means to it. A **CT-calibration factor** derived from Aurora's
metered kWh removes the current-transformer bias, so the rate model's own error is visible
separately from the metering error.

Two repos:
- **`~/Projects/energy-sim`** — the simulator (standalone git repo).
- **`~/Projects/HomeAssistantConfig`** — HA config; holds `scripts/aurora_import.py` (the Aurora
  importer we rewrote, still uncommitted) and `infra/vmalert/powerflow.yml` (the `pf:*` metric
  definitions).

## Dev environment

Pure-stdlib runtime; pytest via the Nix flake. **`pytest` is not on the global PATH** — always:
```sh
cd ~/Projects/energy-sim
nix develop --command pytest tests/        # 85 tests, green
nix develop --command python -m energy_sim {export,cost-report,validate} ...
```

## CURRENT RESULT (June 2026, the validation month)

```
THE NUMBER — modelled net cost vs what Aurora actually billed:
  as measured   modelled $178.43  actual $180.91  Δ -$2.47  -1.4%
  CT-calibrated modelled $181.64  actual $180.91  Δ +$0.73  +0.4%
  CT calibration: import x1.027   export x1.071

Check 1 — rate/formula in isolation:  all four legs PASS at $0.00 delta
  (peak $58.52, off-peak $84.34, export credit $7.31, supply $45.35)
Check 2 — peak-window classifier:     683/710 hours agree, 27 disagree  <-- see open finding
```

Reproduce:
```sh
nix develop --command python -m energy_sim export --month 2026-06 --out data/energy_hourly_2026-06.csv
nix develop --command python -m energy_sim cost-report --in data/energy_hourly_2026-06.csv
nix develop --command python -m energy_sim validate  --in data/energy_hourly_2026-06.csv
```

## THE ONE OPEN DECISION (awaiting the user)

The peak-window rule applies its **Mon–Fri test to the UTC date**, while its 21:00–24:00Z block
belongs to the **next local day**. All 27 classifier mismatches are this single error:

| UTC slot | is locally | we charge | Aurora charges |
|---|---|---|---|
| Fri 21–24Z (x4/mo) | Sat 07–10 | peak | off-peak |
| Sun 21–24Z (x5/mo) | Mon 07–10 | off-peak | peak |

Worth **-$1.05** on the June bill (we *under*-charge), so fixing it moves the headline residual
from +$0.73 to roughly +$1.8 — the model gets more correct and the number gets slightly worse.

Fixing it means evaluating the window in `Australia/Hobart` instead of fixed UTC hours, which
also resolves the DST caveat R1 deferred — but **diverges from `powerflow.yml`**, which has the
identical bug and would need the same fix + a redeploy. R1 explicitly listed the DST-aware peak
window as out of scope, which is why this was left alone rather than just fixed.

## What's built (energy-sim) — DDD, TDD, 85 tests green

```
src/energy_sim/
  domain/         money, energy (EnergyQuantity + from_average_watts), reading (IntervalReading),
                  tariff (PeakWindow/TariffPeriod/Tariff — peak_rate/offpeak_rate/import/export/supply),
                  device (Device base + DeviceRole{GRID,SOLAR,LOAD} + SingleMeterDevice),
                  grid_connection (GridConnection + GridInterval, dual import/export channels),
                  solar_inverter, house_load, site (Site aggregate root + energy_balance_errors),
                  cost (CostBreakdown: usage_cost, net_cost)
  application/    cost_calculator (CostCalculatorService.calculate(site, tariff) -> CostBreakdown),
                  calibration (CalibrationFactors, calibration_factors(snapshot), calibrate(site,..)),
                  validation (ValidationService + LineComparison/ClassifierResult/ValidationReport)
  infrastructure/ victoriametrics (query_range + export clients, both parsed by pure functions),
                  csv_store (SnapshotRow/Snapshot, read/write, hydrate Site, aurora aggregates),
                  tariff_loader (config/tariffs.toml -> Tariff),
                  exporter (POWER/AURORA_KWH queries + AURORA_DOLLAR selectors + assemble_rows)
  interface/cli.py  export / cost-report / validate ; month_bounds ; render_cost_report /
                  render_validation (pure)
config/tariffs.toml   Aurora Tariff 93 (source of truth).
```

**Device model is deliberately minimal** (user request): only GridConnection/SolarInverter/
HouseLoad. Battery/EV/HotWater/HeatPump arrive when actually built (iteration 2+).

Resolution is a parameter throughout (`--step-seconds`, default 3600); `IntervalReading` carries
`interval_s`. 5-min is a drop-in.

## The data pipeline reality (discovered the hard way — don't re-derive)

VictoriaMetrics at **`http://192.168.88.152:8428`** (reachable from the dev box).

- **`pf:*` power flows** (W): `pf:grid_import_w`, `pf:grid_export_w`, `pf:solar_w`,
  `pf:consumption_w`. Defined in `HomeAssistantConfig/infra/vmalert/powerflow.yml`. Read low vs
  Aurora — measured at **+2.7% import, +7.1% export** for June 2026 (the older "7–16%" figure
  was over the whole raw history, not this month).
- **Aurora billed kWh** — **hourly**, tariff-split: `sensor.aurora_hourly_kwh_t93_peak`,
  `_t93_offpeak`, `_t140` (export). Metric `homeassistant_sensor_energy_kwh`.
- **Aurora billed DOLLARS** — **DAILY only**: `sensor.aurora_daily_dollar_{t93_peak,t93_offpeak,
  t140,other,total}`, metric `homeassistant_sensor_state`, stamped at each billed day's local
  midnight = **14:00:00Z** in AEST winter. `other` = the fixed supply charge; `total` = all-in.
  **Must be read via `/api/v1/export`** (raw samples) — `query_range` at any sub-day step smears
  each daily value across 24 hours, and summing that over-counts ~24x.
- **A month is a LOCAL billing month, end-exclusive.** `month_bounds()` resolves `--month` in
  `Australia/Hobart`; June 2026 = `2026-05-31T14:00Z .. 2026-06-30T14:00Z`, 720 rows, exactly 30
  billed days. A UTC month window instead drops AEST Jun 1 and gains AEST Jul 1 — and Jul 1 bills
  at the FY2026-27 supply rate, so the supply column stops being a clean multiple of the day rate
  (a useful tell that the window is wrong).
- **The old "$189.19 June target" was wrong** — it summed 31 daily points for a 30-day month
  (inclusive end bound). The correct billed total for AEST June 2026 is **$180.91**.

### Tariff constants — TWO of them were wrong in the source docs

`config/tariffs.toml` is the source of truth. Recovery method (same one that produced the supply
charge): billed dollars for a leg ÷ Aurora's own metered kWh for that leg, per day. Every day of
June 2026 returned an identical rate, so these are exact billed rates, not fits.

| | FY2025-26 | FY2026-27 |
|---|---|---|
| peak c/kWh | **35.4782** (docs said 31.948) | 36.1878 |
| offpeak c/kWh | **16.6862** (docs said 14.876) | 17.02 |
| export/FiT c/kWh | 8.782 (docs correct) | 9.276 |
| supply c/day | **151.1814** (recovered; docs had "—") | 172.3469 |

The recovered rates are exactly **+2.0000%** into the FY2026-27 rates on *both* legs; the doc
values implied +13.3%/+14.4% and a different rise per leg. That cross-check is what confirmed
them. With these in place all four rate legs validate at **$0.00** delta.

## Aurora auth (the rabbit hole — so you don't repeat it)

- `scripts/aurora_import.py` was **rewritten** to use the **`auroraplus` library** (not
  hand-rolled auth). The old `id_token → LoginToken` flow only worked for 1h. The library
  refreshes off the long-lived **`RefreshToken` cookie** ("Keep me logged in"), which **rotates
  on every use** — so it can't be shared out-of-band with HA (whoever refreshes first invalidates
  the other).
- Token persisted at `HomeAssistantConfig/scripts/.auroraplus_tokens.json` (git-ignored via
  `scripts/.*_tokens.json`). `load_token()` prefers it, else reads HA's config entry.
- The `auroraplus` lib lives in a scratchpad venv; recreate if gone with
  `pip install "auroraplus @ git+https://github.com/LeighCurran/AuroraPlus@main"`, then:
  ```sh
  cd ~/Projects/HomeAssistantConfig
  <venv>/bin/python scripts/aurora_import.py --days 120     # hourly kWh + daily dollars -> VM
  ```
- Backfill done: **120 days** (back to 2026-03-26). Re-run only if extending.
- NOTE: HA's own Aurora integration will likely need **one re-auth** (its cookie was burned
  during investigation). User is aware.

## Gotchas

- Don't query VM with the bare entity as metric name — use `homeassistant_sensor_state{entity="..."}`.
- VM's `start`/`end` are **inclusive**; `fetch_rows` pulls `end` back 1s so consecutive months
  don't share a boundary sample.
- `nix develop --command` prints a "devenv ready" banner to stderr; ignore it.
- The energy-balance check reports 16 intervals over 0.01 kWh in June — a data-quality signal
  about the pf:* series, not a cost bug. Not yet investigated.

## Not done

- The open classifier decision above.
- `HomeAssistantConfig/scripts/aurora_import.py` is still uncommitted in that repo.
- `infra/vmalert/powerflow.yml` still carries the UTC-weekday peak-window bug (and its own copy
  of the two wrong tariff rates — worth checking `pf:import_rate_c_kwh` against 35.4782/16.6862).
