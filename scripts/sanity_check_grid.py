"""Ground-truth the simulator: does grid DERIVED from (solar, load) match the MEASURED grid?

For every committed snapshot, build the measured grid and the grid simulated from solar+load,
cost both against the real tariff, and report the residual. This is the sanity check that the
model's central move — treating grid as an output of solar and load — reproduces reality before
we trust it to answer what-if questions.

Run: PYTHONPATH=./src python3 scripts/sanity_check_grid.py
"""
from __future__ import annotations

import glob
from pathlib import Path

from energy_sim.application.cost_calculator import CostCalculatorService
from energy_sim.application.grid_simulation import simulate_grid
from energy_sim.infrastructure.csv_store import read_snapshot
from energy_sim.infrastructure.tariff_loader import load_tariff

REPO = Path(__file__).resolve().parents[1]
TARIFF = load_tariff(str(REPO / "config" / "tariffs.toml"))


def kwh(grid, attr):
    return sum(getattr(gi, attr).kwh for gi in grid.intervals())


def main():
    cost = CostCalculatorService()
    tot = {"m_imp": 0.0, "s_imp": 0.0, "m_exp": 0.0, "s_exp": 0.0}
    m_cost_total = s_cost_total = 0.0
    worst = []
    for f in sorted(glob.glob(str(REPO / "data" / "months" / "*.csv"))):
        snap = read_snapshot(f)
        site = snap.to_site()
        if site.solar is None:
            continue
        sim = simulate_grid(site.solar, site.load)
        from energy_sim.domain.site import Site
        sim_site = Site(name="sim", grid=sim)

        m_imp, s_imp = kwh(site.grid, "import_energy"), kwh(sim, "import_energy")
        m_exp, s_exp = kwh(site.grid, "export_energy"), kwh(sim, "export_energy")
        m_cost = float(cost.calculate(site, TARIFF).net_cost.dollars)
        s_cost = float(cost.calculate(sim_site, TARIFF).net_cost.dollars)
        tot["m_imp"] += m_imp; tot["s_imp"] += s_imp
        tot["m_exp"] += m_exp; tot["s_exp"] += s_exp
        m_cost_total += m_cost; s_cost_total += s_cost
        worst.append((abs(s_cost - m_cost), Path(f).stem, m_cost, s_cost))

    print("Whole record — measured grid vs grid simulated from (solar, load):")
    print(f"  import kWh : measured {tot['m_imp']:8.0f}   simulated {tot['s_imp']:8.0f}   "
          f"Δ {tot['s_imp']-tot['m_imp']:+.0f}")
    print(f"  export kWh : measured {tot['m_exp']:8.0f}   simulated {tot['s_exp']:8.0f}   "
          f"Δ {tot['s_exp']-tot['m_exp']:+.0f}")
    print(f"  net kWh    : measured {tot['m_imp']-tot['m_exp']:8.0f}   "
          f"simulated {tot['s_imp']-tot['s_exp']:8.0f}   "
          f"Δ {(tot['s_imp']-tot['s_exp'])-(tot['m_imp']-tot['m_exp']):+.0f}  (identity check)")
    print(f"  net COST   : measured ${m_cost_total:8.2f}   simulated ${s_cost_total:8.2f}   "
          f"Δ ${s_cost_total-m_cost_total:+.2f}  ({100*(s_cost_total-m_cost_total)/m_cost_total:+.1f}%)")
    print("\n  Why non-zero: when an hour has BOTH import and export (sub-hour churn), measured")
    print("  keeps both but derived nets them, so derived imports/exports less and costs slightly")
    print("  less. Net kWh matches by construction; the cost gap is the sub-hour churn, priced.")
    print("\n  Largest monthly cost residuals:")
    for d, name, mc, sc in sorted(worst, reverse=True)[:5]:
        print(f"    {name}: measured ${mc:.2f}  simulated ${sc:.2f}  Δ ${sc-mc:+.2f}")


if __name__ == "__main__":
    main()
