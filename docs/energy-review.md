# Household energy review — November 2026

Reference record of what the simulator and the Home Assistant / VictoriaMetrics data show about
this house's energy. FY2026-27 rates unless noted. Dates are absolute — device-level metering
begins partway through the record (see *Data coverage*).

## Summary

- Annual consumption ≈ 9,000–10,600 kWh/yr. The largest category is ordinary household load.
- The heat-pump outdoor unit was degraded and was repaired ~late Aug / early Sep 2026. The repair
  saves ~$250–300/yr: ~30% of the heat pump's own energy, plus ~$240/winter of resistive backup
  heating it had required. That is ~25% of the annual net bill, almost all winter load. First clean
  post-repair winter for confirmation: Jun–Aug 2027.
- A battery is not economic. Off-grid is not feasible. A zero net bill is possible only while the
  feed-in tariff survives (~2× the panels, no battery).

## Where the electricity goes

Whole-home ≈ 9,000–10,600 kWh/yr. Over the window where every device is metered (23 Jul – 3 Nov
2026), annualised:

| Load | Annual | Share | Notes |
|---|---|---|---|
| Residual (everything else) | ~5,650 kWh | ~53% | ordinary household load |
| Heat pump | ~2,280 kWh | ~21% | ~$150/yr (post-repair) |
| Hot water | ~1,400 kWh | ~13% | ~$200/yr grid; mostly 3–5am off-peak |
| EV (Zappi) | ~1,280 kWh | ~12% | window figure; full-year ~2,600 kWh / ~$320 — see *EV charging* |

EV and heat-pump loads are seasonal and the window (late Jul – early Nov) is spring-weighted, so
their full-year figures (in their own sections) are higher than this snapshot.

Residual is a flat ~0.6–0.7 kW through the day with no midday trough, consistent with working from
home: computers, monitors, lighting, daytime cooking, and an occupied house heated midday. Standby
base ~200 W (~70 W with everything off). Optional trims: sleep the monitor (~$30–75/yr), switch off
the electronics bench when idle.

## Battery: not economic

Via the simulator (`simulate_grid` → `Battery` dispatch → re-cost), self-consumption, 5 kW, 90%
round-trip:

- ~$166/yr @5 kWh, ~$220/yr @10 kWh, ~$273/yr @30 kWh. Marginal value collapses past ~7 kWh.
- Payback (10 kWh) 23–41 yr at $500–900/kWh net, vs ~10 yr warranty.
- A 30 kWh unit (e.g. Sungrow SBH300) is the worst value on the curve — the last 20 kWh over a
  10 kWh unit earns ~$50/yr total.

Sensitivities:

- **Zero feed-in tariff:** battery value roughly doubles (~$433/yr @10 kWh, ~12 yr payback at
  $500/kWh net) — stored solar then displaces import at the full rate rather than the spread over
  the FiT.
- **Capturing all surplus is impossible:** the house generates ~7,200 kWh/yr surplus but draws
  ~5,400 kWh/yr, so ≥1,840 kWh/yr can never be used; even an infinite battery captures only ~61%
  (summer surplus cannot be stored to winter).
- **Off-grid is not feasible:** Apr–Sep generation is below consumption (Jul: ~16 vs ~42 kWh/day),
  a generation shortfall no battery can cover. True off-grid needs ~5× the panels and 50–100 kWh
  (~$75–150k); 95% self-sufficient is ~3× solar + 30 kWh plus a generator for the coldest weeks.
  Annually the house is net-positive (~+1,840 kWh/yr); the grid acts as free seasonal storage.
- **Zero net bill:** possible only while the FiT survives — ~2× the panels (no battery) offsets the
  net bill including the ~$629/yr supply charge. Under a zero FiT it is impossible while
  grid-connected: nothing offsets the fixed supply charge short of disconnecting.

The EV on eco+ is the best use of surplus (~20–40c/km displaced driving vs a battery's ~8–11c/kWh
arbitrage).

## Heat pump

The heat-pump outdoor unit was degraded and was repaired ~late Aug / early Sep 2026. Weather-matched
(same outdoor temp, before vs after):

| Outside | Pre-repair | Post-repair | Power cut |
|---|---|---|---|
| 8–10°C | 497 W | 391 W | −21% |
| 10–12°C | 359 W | 275 W | −23% |
| 12–14°C | 269 W | 157 W | −42% |

~20–50% less electricity for the same indoor temperature; pre-repair runtime ~95%. Repaired
baseline ~$150/yr (~30% less energy than broken).

Thermal characteristics (calibrated from data):

- Unit efficiency is flat across the cold range (25–31 W/°C), no cold-weather COP collapse.
- Thermal time constant τ ≈ 32h from coast-down with heating off (~0.5°C/h loss at a 15°C gap);
  night-time value likely 15–25h after accounting for daytime solar gain. The fabric holds heat
  well, so pre-heating on off-peak/solar and coasting through peak is viable.
- Per-day heating energy ~triples from a mild day to a cool one; the common 8–14°C days carry most
  of it.
- Heating is already ~76% off-peak; shifting the remainder saves ~$100/yr.

**Stratification (open comfort issue):** the Daikin's sensor sits near the ceiling and reads ~1–3°C
above its setpoint while the occupied zone is cold, so the setpoint is driven toward 30°C and the
fan to max. Fix: thermometers at seated height and in a far room to measure the gap, then a ceiling
fan on low to mix (~$50). Removes the need for resistive backup.

## Resistive heating

Resistive backup (a 1200 W fan heater, plus an oil column heater for ~a month) was used while the
heat-pump unit was degraded, mostly deep winter (Jun–Jul), before device metering. It is recoverable
from whole-home `pf:*` consumption (back to 2023).

June–July 2026 residual (whole-home minus metered heat pump and EV), by local hour:

- a flat ~1.5 kW block overnight (8pm–8am) — a 1200 W heater plus ~0.3 kW base;
- a 3–4am spike (hot-water off-peak boost);
- cooking peaks ~noon (~0.9 kW) and 5–7pm (~1.5 kW); ~0.5 kW through the day.

Overnight residual ~21 kWh/night; less base + hot water (~7 kWh) leaves ~14 kWh/night of resistive
heat (≈ 1200 W × 12h). Over a ~90-night heating season: ~1,250 kWh ≈ ~$240/winter (~19c/kWh; range
~$180–320 depending on nights and peak/off-peak mix). Resistive (COP 1) vs heat-pump COP ~3.5 is
~3.5× the cost per unit of heat. The repaired unit covers the coldest days, so resistive backup is
no longer needed; this ~$240/winter is part of the ~$250–300/yr repair value.

## EV charging

Total charging ~2,600 kWh/yr (last 12 months, ~13,800 km). Cost ~$320/yr = **~$125/yr grid import
(cash)** + **~$198/yr forgone feed-in credit** on diverted solar. ~84% of charging is solar (eco+).
Petrol equivalent for the same distance ~$1,700/yr, so the EV saves ~$1,380/yr.

The solar/grid split is the Zappi's own measurement (diverted vs boosted channels), not derived by
subtracting solar generation from charging. That subtraction over-attributes grid to the car —
~46% solar vs the device's ~84% — because at hourly resolution solar and charging within the same
hour are mixed, and the house/solar meters (which read low) don't align with the Zappi's. Cost uses
the reliable-split window (Apr–Oct 2026); winter charges more and from less solar, so the true
annual figure is likely somewhat higher.

## Hot water

Metered by the Shelly EM, entity **`sensor.hw_cylinder_power`** (the
`shellyemg3_…_energy_meter_1_power` channel is a dead duplicate reading zero). ~4.0 kWh/day
(~1,476 kWh/yr), ~$200/yr grid. Heats mostly **3–5am on off-peak** (64%), ~26% from solar diversion
via the Catch relay. Shifting more to midday solar would save ~$20/yr.

## Data coverage & caveats

Device-level scraping into VictoriaMetrics began **2026-05-22**; the committed whole-home `pf:*`
snapshots go back to 2023-11.

- **Heat pump** power + temps: from 2026-05-22. The window spans the repair (late Aug / early Sep);
  split pre/post before comparing.
- **Hot water** (`sensor.hw_cylinder_power`): from 2026-07-23.
- **EV**: total charging is reliable from Aug 2025 (myenergi backfill), validated against VM for the
  overlap. The **solar/grid split is only recorded from ~Apr 2026** — before that the grid-boost
  field (`h1b`) is not populated and all charging is filed under the diverted field (`h1d`)
  regardless of source. 27% of pre-April charging was deep-night (11pm–5am), i.e. grid, confirming
  the pre-April data does not distinguish solar from grid. A device-measured summer split will not
  exist until after Dec 2026 – Feb 2027.

## Action items / open levers

1. **Stratification fix** — thermometers (seated height + a far room) → a ceiling fan (~$50).
   Comfort, and keeps resistive backup unneeded.
2. **Sleep the monitor** (~$30–75/yr).
3. Optional: a plug meter on the electronics bench / computing cluster to split the residual
   precisely.
4. The hot-water Shelly exposes a dead duplicate channel; could be removed in HA.
5. Re-check winter-2027 data against the expected ~$250–300/yr heating saving.
