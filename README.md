# energy-sim

A home energy-cost / scenario simulator built on the cleaned power-flow data from the
`HomeAssistantConfig` project (VictoriaMetrics `pf:*` layer + Aurora Plus billed data).

**Iteration 1 (current):** replay real grid import/export, compute the Aurora Tariff 93 cost,
and validate it against the actual Aurora Plus billed dollars. Whole-home only — no per-device
disaggregation, no battery yet.

The design is DDD-structured (a `Site` aggregate root owning a device topology) so later
iterations — battery economics first (see `REQUIREMENTS.md`), then EV / hot-water / heat-pump
modelling — add a `Device` subtype rather than restructure.

See `REQUIREMENTS.md` for the incremental requirements log (this project doubles as a repeatable
AI-assisted-codegen experiment: each requirement change is recorded so the build can be replayed).

## Dev environment

Pure-stdlib runtime; `pytest` for tests, provided by the Nix flake:

```sh
nix develop            # enters a shell with python3 + pytest; sets PYTHONPATH=./src
pytest                 # run the test suite
```

## Data

Aurora billing / `pf:*` power flows live in VictoriaMetrics at `http://192.168.88.152:8428`
(reachable from the dev box). The simulator snapshots a period to a committed CSV under `data/`
for reproducible runs, then computes/validates against that snapshot.

```sh
python -m energy_sim export --month 2026-06 --out data/energy_hourly_2026-06.csv   # default --step-seconds 3600
python -m energy_sim cost-report --in data/energy_hourly_2026-06.csv
python -m energy_sim validate --in data/energy_hourly_2026-06.csv
```

Resolution is a parameter (`--step-seconds`); `300` gives a 5-min snapshot with no domain changes.
Aurora ground truth is hourly, so validation buckets finer series up to 1h before comparing.

## Tariff constants

`config/tariffs.toml` is the authoritative copy of Aurora Tariff 93 rates (previously only in
prose / un-versioned VM series). See that file for the FY periods, peak window, and data gaps.
