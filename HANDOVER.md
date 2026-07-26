# Handover — what to do next

A **work queue**, not documentation. Delete it when the queue empties. How the system works lives
in [`docs/`](docs/) and `REQUIREMENTS.md`; the reasoning behind each task lives on its Trello card.
This file only says *what is outstanding, in what order, and why*.

## Where things stand

Iteration 1 is merged (`ddf600a`). **HI-64 is done** and sitting on branches in both repos, not yet
merged: `energy-sim` `feat/fail-noisily-or-retry`, `HomeAssistantConfig` `feat/imports-fail-noisily`.

Verified, not assumed:

```sh
nix develop --command pytest tests/                                  # 120 green (was 98)
nix develop --command python scripts/validate_all_months.py 2023-11 2026-06
```

32 months, **$2,302.22** billed → **-0.50%** as measured, **-0.07%** CT-calibrated, with 100%
peak/off-peak classifier agreement in every month — **unchanged by HI-64**, which was the point.
Re-run the sweep before and after any change here; it takes a few minutes and it is the regression
test that matters. A full re-export now also proves it: 27 of 32 snapshots byte-identical, the
other 5 differing only in solar/consumption cells that were `0.0` and are now blank.

In `HomeAssistantConfig`, `python3 -m unittest discover scripts` is 39 green (was 13).

## The queue

**1. HI-63 — energy-balance label + the June breaches** · https://trello.com/c/VoKuhnaR
The exporter zero-fill half is **already done** in HI-64 — `kwh_from_watts` propagates `None` and
all four flow columns are optional. What is left is the relabelling, and a correction:

> **The card's stated cause is wrong.** A fresh export of June 2026 has **zero** blank cells:
> `pf:solar_w` and `pf:consumption_w` have a sample at every hourly step. So the zero-fill did
> **not** manufacture those 13 breaches, and "expect: coverage gaps, now visible rather than
> fabricated" will not hold. Something else explains them — find out what before relabelling.
> Real coverage gaps do exist, but in 2024-01, 2024-06, 2024-07, 2024-09 and 2026-05 (23 rows).

Also still open on that card: myenergi CT placement, and the Shelly EM hot-water gap.

**2. HI-62 — ruff + mypy + CI** · https://trello.com/c/4W94Wupg
Last, deliberately: `ruff format` touches nearly every file. Sequence the reformat as its own
commit. Three pre-existing unused imports are waiting for it (`isolarcloud_import.py` `time` and
`timezone`, `solaranalytics_import.py` `timezone`) — left alone so they would not be buried in
the HI-64 diff.

## Needs you, not me

- **iSolarCloud credential.** Its stored refresh token is dead (`invalid_grant`) and HA holds the
  only live one in memory, rotating it on use — so the "copy a fresh token from HA" recovery does
  not work. HA itself is **fine**; do not re-authenticate it on my account. A clean fix needs a
  separate app registration for the importer. The series is now stale from **2026-07-19**.
- **myenergi's history feed is behind.** The Zappi itself is healthy (live CTs updating every
  ~30s), but `cgi-jdayhour` served only 5 hours for 2026-07-24 and nothing since. Nothing to fix
  on our side; just do not read the flat hourly series as a dead device.
- **myenergi CT placement** — `pf:consumption_w` 1757 W vs myenergi `home_consumption` 919 W over
  June. Independent CTs, so real information, but a 60% gap suggests they are not on the main
  incomer. Worth knowing before anyone treats it as a second whole-home reference. On HI-63.
- **Shelly EM hot water** returned no data for June 2026 despite being a live entity. Unexplained.

## Data that is gone, so nobody re-checks it

Established by scanning the sources directly on 2026-07-26, not inferred:

- **zappi 2026-02-05 .. 02-18** (14 days) and **2026-04-24 .. 04-25** — myenergi returns zero
  entries. This is the hole that the old 7-empty-day rule mistook for the end of the record.
- **Catch daily before ~2026-02-23** — the Monocle API no longer serves it. The importer used to
  stop after two empty chunks, which hid the fact; it now walks to `--earliest` and reports it.

## Working notes

- `pytest` is not on the global PATH — always `nix develop --command ...`.
- Snapshots under `data/months/` are git-ignored and reproducible; delete them to force a
  re-export from VictoriaMetrics.
- The strongest cheap check on any change to the exporter: **the answer must not move when
  `--step-seconds` changes.** 3600 / 900 / 300 should agree to the cent.
- Aurora is the only independent truth in the system. When a source and Aurora disagree, Aurora
  wins — that is how the wrong tariff rates, the hour-shifted imports and the peak window were all
  found.
- **A blank flow cell means "nothing measured", never "zero".** `Snapshot.incomplete_rows()` is
  how a partially-covered interval shows up; totals treat a blank as no energy, but only after
  the row has said so.
- **Do not use `aurora_hourly_kwh_t93_peak` as a coverage proxy.** It is legitimately empty on
  Sundays (all off-peak), which reads as a weekly hole that is not there. Peak + off-peak sums
  to 24 every day; check the pair, or `aurora_daily_dollar_total`.
