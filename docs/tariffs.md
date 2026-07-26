# Tariff rates

`config/tariffs.toml` is the authoritative copy of the Aurora Tariff 93 rates. Where a published
figure and the bill disagree, **the bill wins** — several published values were wrong.

## Recovering a rate from the bill

Divide Aurora's billed dollars for a leg by Aurora's own metered kWh for that leg, per day:

```python
implied_c_per_kwh = 100 * billed_dollars_for_the_day / metered_kwh_for_the_day
```

Take the median across a financial year. If a period's rate is genuinely constant the daily values
come out **identical**, not merely close — that is the signal you have an exact rate rather than a
fit. The method reproduces the two known periods (FY2025-26, FY2026-27) exactly from data, which is
what validates it for the periods that were unknown.

Aurora changes rates on 1 July, so recover per financial year.

## What this turned up

| | published / on file | as actually billed |
|---|---|---|
| FY2025-26 peak | 31.948 | **35.4782** |
| FY2025-26 off-peak | 14.876 | **16.6862** |
| FY2025-26 supply | *"—" (missing)* | **151.1814** c/day |
| FY2023-24, FY2024-25 | *unknown* | recovered — see the config |

The published FY2025-26 values imply an uneven +13.3% / +14.4% jump into FY2026-27; the recovered
ones imply exactly **+2.0000%** on both legs, which is what a single annual price rise looks like.
The feed-in tariff needed no correction.

Cross-check any recovered rate this way before trusting it — a rate that produces an implausible
year-on-year step is probably wrong.

## See also

- [aurora-data.md](aurora-data.md) — the clocks that decide which hours a rate applies to
- `config/tariffs.toml`, `src/energy_sim/domain/tariff.py`
