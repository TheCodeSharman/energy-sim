# energy-sim

A home energy-cost / scenario simulator built on the cleaned power-flow data from the
`HomeAssistantConfig` project (VictoriaMetrics `pf:*` layer + Aurora Plus billed data).

Replays real grid import/export, computes the Aurora Tariff 93 cost, and validates it against the
dollars Aurora actually billed. Whole-home cost accounting, plus a battery what-if (R2) that
dispatches a modelled battery over the real flows and re-costs them; per-device disaggregation
(EV/Zappi, hot water, heat pump) is R3, not yet built.

The design is DDD-structured (a `Site` aggregate root owning a device topology) so later scenarios
add a `Device` subtype rather than restructure.

## Dev environment

Pure-stdlib runtime; `pytest` for tests, provided by the Nix flake:

```sh
nix develop            # python3 + pytest; sets PYTHONPATH=./src
pytest                 # run the test suite
```

## Usage

Snapshot a period to CSV, then compute and validate against that snapshot, so runs are
reproducible:

```sh
python -m energy_sim export --month 2026-06 --out data/energy_hourly_2026-06.csv
python -m energy_sim cost-report --in data/energy_hourly_2026-06.csv
python -m energy_sim validate    --in data/energy_hourly_2026-06.csv
```

Battery what-if — the saving a modelled battery would make against the no-battery baseline for a
snapshot (self-consumption dispatch; `--power-kw` default 5, `--round-trip` default 0.9):

```sh
python -m energy_sim battery --in data/energy_hourly_2026-06.csv --usable-kwh 10
```

Resolution is a parameter (`--step-seconds`, default 3600); `300` gives a 5-min snapshot with no
domain changes. A correct model gives the same answer at every resolution — if two disagree, see
[docs/timestamps.md](docs/timestamps.md).

To check the model against the whole record rather than one month:

```sh
python scripts/validate_all_months.py 2023-11 2026-06
```

Validate the **whole series**, not a single month. Compensating errors cancel: a winter month
validated cleanly while the model was wrong for half of every year.

## What a blank cell means, and what an exit code means

A blank flow column in a snapshot is an interval where **nothing was measured** — not zero
energy. Reads that cannot be completed are retried and then raise; they never come back as an
empty series, and `export` reports how many intervals were built from partial `pf:*` coverage.
Both the CLI and the whole-series sweep exit non-zero if any month is missing from their
totals, because a partial answer printed confidently is worse than no answer: a transient
failure once turned 32 months into 29 and $2,302 into $1,817 while looking entirely healthy.

## Docs

- [docs/aurora-data.md](docs/aurora-data.md) — Aurora's two clocks, daily-vs-hourly cadence, billing months
- [docs/timestamps.md](docs/timestamps.md) — the interval convention, and the resolution-drift symptom
- [docs/tariffs.md](docs/tariffs.md) — recovering rates from the bill when published figures are wrong
- [docs/energy-review.md](docs/energy-review.md) — findings from using the model: per-load costs,
  the battery/off-grid/zero-bill answers, and the heat-pump repair
- `config/tariffs.toml` — the authoritative rates, periods and peak window
- `REQUIREMENTS.md` — the incremental requirements log; this project doubles as a repeatable
  AI-assisted-codegen experiment, so each requirement change is recorded to allow a replay

## Data

`pf:*` power flows and Aurora billing live in VictoriaMetrics on the home network, reachable from
the dev box; `--vm-url` overrides the default.
