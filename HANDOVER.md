# Handover — what to do next

A **work queue**, not documentation. Delete it when the queue empties. How the system works lives
in [`docs/`](docs/) and `REQUIREMENTS.md`; the reasoning behind each task lives on its Trello card.
This file only says *what is outstanding, in what order, and why*.

## Where things stand

Iteration 1 is merged (`ddf600a`). Verified, not assumed:

```sh
nix develop --command pytest tests/                                  # 99 green
nix develop --command python scripts/validate_all_months.py 2023-11 2026-06
```

32 months, **$2,302.22** billed → **-0.50%** as measured, **-0.07%** CT-calibrated, with 100%
peak/off-peak classifier agreement in every month. Re-run the sweep before and after any change
here — it is the regression test that matters, and it takes a few minutes.

`HomeAssistantConfig` is at `fa79c0b`, clean. Both repos pushed.

## The queue

Do them in this order. Each is a standalone PR; none is blocked on the others except where noted.

**1. HI-64 — imports must fail noisily or retry** · https://trello.com/c/pWOXNbP9
Highest value. An import can currently truncate five months of data, log a warning, report
success and exit 0 — that happened, and was caught only by diffing row counts by hand. Spans both
repos. The rule: transient failure → retry with backoff; mid-range gap → record and continue,
never truncate; end-of-data → stop and say so distinctly.

**2. HI-63 — energy-balance label + exporter zero-fill** · https://trello.com/c/VoKuhnaR
Overlaps HI-64 on the exporter's `series.get(ts, 0.0)`, which fabricates "0 kWh" for an hour that
has no reading. Do that part once, in whichever lands first. The rest is relabelling a check that
detects incomplete coverage, not energy balance.

**3. HI-62 — ruff + mypy + CI** · https://trello.com/c/4W94Wupg
Last, deliberately: `ruff format` touches nearly every file, so it would bury the other two.
Sequence the reformat as its own commit.

## Needs you, not me

- **iSolarCloud credential.** Its stored refresh token is dead (`invalid_grant`) and HA holds the
  only live one in memory, rotating it on use — so the "copy a fresh token from HA" recovery does
  not work. HA itself is **fine**; do not re-authenticate it on my account. A clean fix needs a
  separate app registration for the importer. Its *stored data* is already repaired, so this only
  blocks future incremental imports.
- **myenergi CT placement** — `pf:consumption_w` 1757 W vs myenergi `home_consumption` 919 W over
  June. Independent CTs, so real information, but a 60% gap suggests they are not on the main
  incomer. Worth knowing before anyone treats it as a second whole-home reference. On HI-63.
- **Shelly EM hot water** returned no data for June 2026 despite being a live entity. Unexplained.

## Working notes

- `pytest` is not on the global PATH — always `nix develop --command ...`.
- Snapshots under `data/months/` are git-ignored and reproducible; delete them to force a
  re-export from VictoriaMetrics.
- The strongest cheap check on any change to the exporter: **the answer must not move when
  `--step-seconds` changes.** 3600 / 900 / 300 should agree to the cent.
- Aurora is the only independent truth in the system. When a source and Aurora disagree, Aurora
  wins — that is how the wrong tariff rates, the hour-shifted imports and the peak window were all
  found.
