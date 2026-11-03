# Household energy review — November 2026

A point-in-time record of what the simulator and the Home Assistant / VictoriaMetrics data say
about this house's energy, so the conclusions don't have to be re-derived. Numbers are at
FY2026-27 rates unless noted. Dates are absolute because device metering only begins partway
through the record (see *Data coverage* below), so "recent" would rot.

## Headline

There is **no expensive fault or hidden load**. The one real problem — a degraded heat-pump
outdoor unit — was already repaired (~late Aug / early Sep 2026) and is the single biggest saving
in here. Everything else is modest, already near-optimal, or explained by working from home.

## Where the electricity goes

Whole-home ≈ 9,000–10,600 kWh/yr. Disaggregated over the window where every device is metered
(23 Jul – 3 Nov 2026), annualised:

| Load | Annual | Share | Notes |
|---|---|---|---|
| Residual (everything else) | ~5,650 kWh | ~53% | normal work-from-home household load |
| Heat pump | ~2,280 kWh | ~21% | repaired; ~$150/yr |
| Hot water | ~1,400 kWh | ~13% | ~$200/yr grid; mostly 3–5am off-peak |
| EV (Zappi) | ~1,280 kWh | ~12% | ~$250/yr net; already optimal on eco+ |

**The residual is not a gremlin.** It is a flat ~0.6–0.7 kW through the *day* (no midday trough) —
the fingerprint of **working from home**: computers + monitors, lighting, lunch cooking, and an
*occupied* house heated midday. The "average household" benchmark understates this because that
average is dragged down by homes empty 8–10h on weekdays. Measured standby base is ~200 W, ~70 W
with everything off — normal. Small optional trims: sleep the monitor (~$30–75/yr), switch off the
electronics bench when idle (already being done).

## Battery: not economic

Via the simulator (`simulate_grid` → `Battery` dispatch → re-cost), self-consumption, 5 kW, true
90% round-trip:

- ~$166/yr @5 kWh, ~$220/yr @10 kWh, ~$273/yr @30 kWh. Marginal value collapses past ~7 kWh.
- Payback (10 kWh) 23–41 yr at $500–900/kWh net, vs ~10 yr warranty. **No.**
- The I Want Energy / Sungrow **SBH300 is 30 kWh** — the worst value on the curve (the last 20 kWh
  over a 10 kWh unit earns ~$50/yr total).

Sensitivities explored:

- **If the feed-in tariff → 0**, battery value roughly **doubles** (~$433/yr @10 kWh, ~12 yr
  payback at $500/kWh net) — borderline, because stored solar then displaces import at the full
  rate instead of the small spread over the FiT. Still a policy bet.
- **Capturing all surplus is impossible** — the house generates ~7,200 kWh/yr surplus but only
  draws ~5,400 kWh/yr, so ≥1,840 kWh/yr can never be used; even an infinite battery captures only
  ~61% (summer glut can't be stored to winter).
- **Off-grid is unrealistic.** Apr–Sep generation is *below* consumption (Jul: ~16 vs ~42 kWh/day),
  so no battery helps — it's a generation shortfall, not storage. True off-grid needs ~5× the
  panels **and** 50–100 kWh (~$75–150k); 95% self-sufficient is ~3× solar + 30 kWh and a generator
  for the last cold weeks. Annually the house is net-positive (~+1,840 kWh/yr) — the **grid is
  already acting as free seasonal storage**.
- **Bill to zero** is possible *only while the FiT survives*: ~2× the panels (no battery) zeroes
  the net bill including the ~$629/yr supply charge. Under a zero FiT it's impossible while
  grid-connected — nothing offsets the fixed supply charge short of disconnecting.

The **EV on eco+ is the best use of surplus** (~20–40c/km displaced driving vs a battery's
~8–11c/kWh arbitrage), which is a large part of why a standalone battery is weak here.

## Heat pump: a repaired fault, not a thermal problem

The worry that "heating is my major cost" was a **degraded outdoor unit**, not the house or the
climate. Weather-matched (same outdoor temp, before vs after the repair):

| Outside | Pre-repair | Post-repair | Power cut |
|---|---|---|---|
| 8–10°C | 497 W | 391 W | −21% |
| 10–12°C | 359 W | 275 W | −23% |
| 12–14°C | 269 W | 157 W | −42% |

~20–50% less electricity for the same indoor temperature — the signature of a failing unit running
flat-out (95% runtime pre-repair) to barely keep up. Corrected repaired baseline: **~$150/yr**
(~30% less energy than broken). The earlier ~$555/yr figure was wrong twice over — contaminated
(broken + repaired blended) *and* over-annualised (a heating-season figure scaled across a
no-heating summer).

Other thermal findings (calibrated from data, no bottom-up geometry needed):

- **Unit efficiency is healthy** — electrical watts per °C of lift are flat across the cold range
  (25–31 W/°C), no cold-weather COP collapse.
- **House holds heat well** — measured thermal time constant τ ≈ 32h from coast-down when heating
  is off (loses ~0.5°C/h at a 15°C gap). It's a thermal battery: pre-heat on off-peak/solar and
  coast through peak. (τ may be flattered by daytime solar gain; true night-time value likely
  15–25h — still heat-retentive.)
- **Energy tracks cold, not runtime** — per-day heating ~triples from a mild day to a cool one;
  the common 8–14°C days carry most of it.
- **Timing has little headroom** — heating is already ~76% off-peak, so shifting the rest saves
  only ~$100/yr. The repair, not re-timing, was the win.

**Open issue — stratification (the one real remaining lever, and it's about comfort not dollars):**
the Daikin's own temperature sensor sits near the ceiling and reads ~1–3°C *above* its setpoint
while the occupied zone is cold — which is why the setpoint gets pushed toward 30°C and the fan to
max (manual destratification). Fix: add thermometers at seated height / a far room to measure the
gap, then a ceiling fan on low to mix (~$50). This is also what makes resistive heating permanently
unnecessary.

## Resistive heating

Fan heater (1200 W at 50%) and a month on an oil column heater were used to paper over the broken
heat pump, mostly in deep winter (Jun–Jul) *before* any device metering, so they can't be isolated
in the data. They were resistive (COP 1) against a heat-pump COP ~3.5 — i.e. ~3.5× the cost per
unit of heat. With the repaired unit (which now has the headroom to cover the coldest days) and a
stratification fix, resistive backup should never be needed again. This is worth more than any
tariff tweak.

## Hot water

Metered by the Shelly EM, entity **`sensor.hw_cylinder_power`** (not the stale
`shellyemg3_…_energy_meter_1_power` channel, which reads zero — a duplicate, ignore it). ~4.0
kWh/day (~1,476 kWh/yr), ~$200/yr grid. Heats mostly **3–5am on off-peak** (64%), only ~26% from
solar diversion via the Catch relay — a minor optimisation would shift more to midday solar, worth
~$20/yr, not pursued.

## Data coverage & caveats

Device-level scraping into VictoriaMetrics began **2026-05-22** (a HA integration/scrape change),
so most per-device series start then; the committed whole-home `pf:*` snapshots go back to
2023-11.

- **Heat pump** power + temps: from 2026-05-22 (includes winter 2026, but *mixed* broken/repaired —
  always split at the repair before trusting a figure).
- **Hot water** (`sensor.hw_cylinder_power`): from 2026-07-23.
- **EV**: total charging reliable 15 months (myenergi backfill to Aug 2025); solar/grid **split**
  only trustworthy from ~Apr 2026 — the historical API omits the grid-boost channel before then,
  so earlier charging is mislabelled 100% "green". A clean device-measured summer won't exist until
  after Dec 2026 – Feb 2027.

## Action items / open levers

1. **Stratification fix** — thermometers (seated height + a far room) → a ceiling fan (~$50).
   Comfort, and keeps resistive heating permanently unneeded. The one worthwhile remaining job.
2. **Sleep the monitor** (~$30–75/yr) — free.
3. Optional: a plug meter on the electronics bench / computing cluster if you ever want the
   residual split precisely.
4. The hot-water Shelly exposes a dead duplicate channel; harmless, but could be removed in HA.
