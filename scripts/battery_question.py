"""'Is a battery worth it?' — answered through the real simulator, not a spike.

Pipeline, all validated domain/application code:
  measured (solar, load)  ->  simulate_grid  ->  SelfConsumptionDispatch(battery)  ->  cost delta

Loads every snapshot into one chronological Site (SoC carries across the whole record), derives
the baseline grid, then for each battery size dispatches a Battery over it and re-costs. The
saving is a difference of two derived-grid costs, so the ~2% sub-hour churn bias cancels.

Run: PYTHONPATH=./src python3 scripts/battery_question.py
"""
from __future__ import annotations

import glob
from pathlib import Path

from energy_sim.application.battery_dispatch import SelfConsumptionDispatch
from energy_sim.application.cost_calculator import CostCalculatorService
from energy_sim.application.grid_simulation import simulate_grid
from energy_sim.domain.battery import Battery
from energy_sim.domain.house_load import HouseLoad
from energy_sim.domain.site import Site
from energy_sim.domain.solar_inverter import SolarInverter
from energy_sim.infrastructure.csv_store import read_snapshot
from energy_sim.infrastructure.tariff_loader import load_tariff

REPO = Path(__file__).resolve().parents[1]
TARIFF = load_tariff(str(REPO / "config" / "tariffs.toml"))


def combined_inputs():
    """One SolarInverter + HouseLoad spanning the whole committed record, in time order."""
    solar = SolarInverter(name="Sungrow")
    load = HouseLoad(name="House")
    n = 0
    for f in sorted(glob.glob(str(REPO / "data" / "months" / "*.csv"))):
        site = read_snapshot(f).to_site()
        if site.solar is None:
            continue
        for r in site.solar.readings:
            solar.add_reading(r)
        for r in site.load.readings:
            load.add_reading(r)
        n += 1
    return solar, load, n


def main():
    solar, load, months = combined_inputs()
    baseline_grid = simulate_grid(solar, load)
    readings = baseline_grid.intervals()
    measured_days = len(readings) / 24.0
    ann = 365.25 / measured_days
    cost = CostCalculatorService()

    base_site = Site(name="baseline", grid=baseline_grid, solar=solar, load=load)
    base_cost = float(cost.calculate(base_site, TARIFF).net_cost.dollars)
    print(f"Simulator: {months} months, {measured_days:.0f} measured days. "
          f"Baseline net cost ${base_cost:.0f} (${base_cost*ann:.0f}/yr).\n")
    print(f"{'usable':>7} {'power':>6} {'$/yr saved':>11} {'marginal $/yr/kWh':>18}")
    print("-" * 48)
    prev_s = prev_c = 0.0
    for cap in [5, 7, 10, 13.5, 20, 30]:
        battery = Battery(name="battery", usable_kwh=cap, max_power_kw=5.0,
                          round_trip_efficiency=0.90)
        adj = SelfConsumptionDispatch().apply(base_site, battery)
        saved = (base_cost - float(cost.calculate(adj, TARIFF).net_cost.dollars)) * ann
        marg = (saved - prev_s) / (cap - prev_c)
        print(f"{cap:>6.1f} {5:>5}k {saved:>10.0f} {marg:>17.0f}")
        prev_s, prev_c = saved, cap

    print("\nPayback (net installed $/kWh after rebate):")
    ten = Battery("b", usable_kwh=10, max_power_kw=5.0, round_trip_efficiency=0.90)
    s10 = (base_cost - float(cost.calculate(
        SelfConsumptionDispatch().apply(base_site, ten), TARIFF).net_cost.dollars)) * ann
    for per_kwh in (500, 700, 900):
        print(f"  10 kWh @ ${per_kwh}/kWh = ${per_kwh*10:,}  ->  {per_kwh*10/s10:.0f} year payback "
              f"(vs ~10 yr warranty life)")


if __name__ == "__main__":
    main()
