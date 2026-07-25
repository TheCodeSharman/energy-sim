# Requirements log

This project is built as a **sequence of incremental requirement changes**, each recorded here.
The intent (HI-61 secondary goal) is that the log is complete enough to *replay* the build — to
re-run the same requirement sequence and get a comparable outcome — so the project doubles as a
repeatable empirical test of AI-assisted code-generation strategies.

Each entry: the requirement as stated, the scope boundary (what is explicitly out), and the
resulting capability. Keep entries append-only; supersede rather than edit history.

---

## R1 — Baseline cost accounting (current)

**Requirement.** Estimate the household's electricity cost from real historical grid
import/export, using the Aurora Tariff 93 rates, and validate the estimate against the actual
Aurora Plus billed dollars.

**Direction.** Simplest possible model first; go slowly. Whole-home only.

**In scope.**
- Pure DDD domain: `Money`, `EnergyQuantity`, `IntervalReading`, `Tariff`/`TariffPeriod`,
  `CostBreakdown`, and a device topology (`Site` aggregate root owning `GridConnection`,
  `SolarInverter`, `HouseLoad`).
- `CostCalculatorService`: `GridConnection` readings + `Tariff` → `CostBreakdown`
  (import cost − export credit + supply charge).
- Machine-readable tariff config (`config/tariffs.toml`).
- Export from VictoriaMetrics to a committed CSV snapshot; default 1h resolution,
  `--step-seconds` parameter so 5-min is a drop-in.
- Validation against Aurora billed data, three checks: (1) rate/formula in isolation using
  Aurora's own kWh, (2) peak-window classifier vs Aurora's peak/off-peak split, (3) end-to-end
  `pf:*` → modelled cost vs Aurora dollars (residual ≈ the known ~7–16% CT-calibration gap).

**Out of scope (deferred).** Battery, per-device disaggregation (EV/hot-water/heat-pump),
supply-charge for FY2025-26 (unknown in source data), DST-aware peak window (fixed UTC offset,
mirroring the vmalert source).

**Capability delivered.** Given a period, produce a cost breakdown and a validation report against
the Aurora bill.

---

## R1.1 — The target is dollars, and metering bias is calibrated out (current)

**Requirement.** The number that matters is the **end-to-end dollar figure**: the modelled net
cost of a month against the dollars Aurora actually billed. kWh is a means to it, not the goal.
Because the household CTs are known to read low, report that comparison **twice** — as measured,
and after removing the metering bias — so the residual attributable to the *rate model* is
visible separately from the residual attributable to *metering*.

**CT calibration.** Derive a scalar per direction from Aurora's own metered kWh
(`import_factor = Aurora import kWh / pf:* import kWh`, likewise export), scale the
`GridConnection` flows by it, and re-cost. Import and export are scaled independently (different
CT paths). Solar and load are not scaled — Aurora gives no ground truth for them.

**Supersedes in R1:**
- *Three checks* → four rate legs (peak, off-peak, export, **supply**) plus a two-line dollar
  end-to-end (as-measured and calibrated). The old "check 3" usage-only comparison is gone;
  net cost vs the billed total replaces it.
- *Supply charge for FY2025-26 unknown* → **recovered** from Aurora's billed daily "Other".

**Also settled here (each proven against Aurora's own data, not assumed):**
- **Aurora's cadences differ.** Billed kWh are hourly; billed **dollars are daily only**. Daily
  dollars must be read as raw samples (`/api/v1/export`) — a `query_range` at any sub-day step
  carries each daily value across all 24 hours, and a monthly sum would over-count it ~24x.
- **A month is a *local* billing month**, not a UTC one, and its end bound is exclusive. Aurora
  stamps each billed day at local midnight (14:00Z in AEST winter), so a UTC window drops the
  month's first billed day and gains the next month's first — a full day of error, at whichever
  supply rate that day falls under.
- **Two FY2025-26 import rates in the source docs were wrong** (peak 31.948, off-peak 14.876).
  The as-billed rates, recovered the same way as the supply charge, are **35.4782** and
  **16.6862** c/kWh — identical on all 30 days of June 2026, and exactly +2.0000% into the
  FY2026-27 rates already on file. See `config/tariffs.toml`.

**Still out of scope.** Battery; per-device disaggregation; DST-aware peak window — but see the
open finding below, which is no longer just a DST question.

**Open finding (→ resolved in R1.2).** The peak-window rule applies
its Mon–Fri test to the **UTC** date, while its 21:00–24:00Z block belongs to the *next local
day*. Over June 2026 this misclassifies 27 hours, all of one shape: UTC-Friday 21–24Z is
Saturday morning locally (charged peak, should be off-peak) and UTC-Sunday 21–24Z is Monday
morning locally (charged off-peak, should be peak). Worth **-$1.05** on the June bill — the model
*under*-charges, so fixing it moves the headline residual further over, not closer. Evaluating
the window in the billing timezone fixes this and the deferred DST caveat together, but diverges
from `infra/vmalert/powerflow.yml`, which has the same bug and would need the same fix.

**Capability delivered.** `validate` reports, for a billing month: four rate legs against
Aurora's billed dollars, the peak-window classifier's agreement, the CT calibration factors, and
the modelled-vs-billed dollar total both as measured and calibrated.

---

## R1.2 — Peak window evaluated in local billing time (current)

**Requirement.** Classify peak/off-peak in the **billing timezone** (`Australia/Hobart`), the way
Aurora bills it — local Mon–Fri, 7–10am and 4–9pm — rather than as fixed UTC hours.

**Supersedes:** R1's "DST-aware peak window" out-of-scope line, and R1.1's open finding. The
deferral assumed this was only a DST refinement; it was also a plain misclassification bug
independent of DST, proven by Aurora's own hourly split.

**What was wrong.** The fixed-UTC form applied its Mon–Fri test to the **UTC** date while its
21:00–24:00Z block belongs to the *next local day*. UTC-Friday 21–24Z is Saturday morning locally
(charged peak, billed off-peak); UTC-Sunday 21–24Z is Monday morning locally (charged off-peak,
billed peak). Separately, the fixed offset ignored DST, putting both blocks an hour out for the
half of the year Tasmania is on AEDT.

**Config shape changed.** `[peak_window]` is now `timezone` + `local_weekdays` (ISO, Mon=1..Sun=7)
+ `local_hours`, replacing `utc_weekdays`/`utc_hours`.

**Result.** The classifier goes from 683/710 to **710/710 hours agreeing** with Aurora — every
mismatch was this one bug. The model was *under*-charging, so the June headline moves from -1.4%
to **-0.8%** as measured, and from +0.4% to **+1.0%** calibrated: more correct, and slightly
further over. Correctness was preferred to the flattering number.

**Deliberate divergence.** `infra/vmalert/powerflow.yml` carries the identical bug in `pf:is_peak`.
Aurora's billed data is the ground truth, not the metrics layer, so the sim was fixed first and
powerflow.yml brought into line separately.

---

## R1.3 — Supply charge is billed per local day (current)

**Requirement.** Charge the fixed daily supply charge once per **local billing day**, not once
per distinct UTC date.

**Why it surfaced.** After R1.2, the CT-calibrated residual (+$1.80) was *larger* than the
as-measured one (-$1.43), which is backwards: calibration removes a known error, so it should
improve the estimate. Decomposing the calibrated residual explained it exactly:

| source | amount |
|---|---|
| peak/off-peak misallocation (1.55 kWh of 670) | +$0.29 |
| **one extra supply day** | **+$1.51** |
| total | +$1.80 |

A 30-day local billing month spans **31 distinct UTC dates**, so counting UTC dates billed one
day too many — every month, for any period. R1's `_supply_charge` noted the UTC-date shortcut as
harmless "because supply is $0/unknown for the validation month"; R1.1 recovered the supply
charge as 151.1814 c/day, which silently invalidated that caveat.

**The as-measured number had been flattered.** The CT under-read (too low) was partly cancelling
this overcharge (too high). Removing one error exposed the other — which is exactly what the
two-line report in R1.1 is for.

**Result.** June 2026 goes from -1.6% as measured to **+0.2%** calibrated — calibration now
improves the estimate ~8x, as it should. The remaining +$0.29 is entirely the peak/off-peak
allocation of energy across hour boundaries, the only error left in the model.

---

## R2 — Battery what-if (planned, not built)

**Requirement (anticipated).** Given a hypothetical home battery (capacity, power, round-trip
efficiency, SoC limits), estimate the cost savings vs the no-battery baseline, and a payback
period under realistic assumptions (battery cost, cycle life, tariff). Decision: yes/no/wait.

**Approach (anticipated).** Add a `Battery` `Device` (a new `DeviceRole`) to the `Site` and run a
self-consumption dispatch strategy that transforms the real `GridConnection` readings into a
battery-adjusted series, then re-run the **same** `CostCalculatorService`. Add sensitivity
analysis (electricity price, battery cost). (Devices are added when built, not pre-declared —
the topology stays minimal to what's exercised.)

---

## R3+ — Device modelling (planned, not built)

**Requirement (anticipated).** Model individual controllable/large loads as their own `Device`
types (EV charger / Zappi, hot-water cylinder / Shelly, heat pump / Daikin) to answer
load-shifting and device-economics questions. Each is added to the `Site` when it is built.
