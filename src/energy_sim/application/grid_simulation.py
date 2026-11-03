"""simulate_grid — derive the grid connection from solar generation and household load.

The grid is an output of the model: every scenario (battery, a different charge schedule, a
heat-pump timer) changes it, so it must be computed from the exogenous inputs rather than read
from a fixed measurement. Per interval the residual of load minus solar is imported if positive
or exported if negative — the inverse of the identity Site already checks.
"""
from __future__ import annotations

from energy_sim.domain.energy import EnergyQuantity
from energy_sim.domain.grid_connection import GridConnection
from energy_sim.domain.house_load import HouseLoad
from energy_sim.domain.reading import IntervalReading
from energy_sim.domain.solar_inverter import SolarInverter


def simulate_grid(solar: SolarInverter, load: HouseLoad,
                  name: str = "derived grid") -> GridConnection:
    solar_by_ts = {r.ts_utc: r for r in solar.readings}
    load_by_ts = {r.ts_utc: r for r in load.readings}

    grid = GridConnection(name=name)
    for ts in sorted(solar_by_ts.keys() | load_by_ts.keys()):
        s = solar_by_ts.get(ts)
        l = load_by_ts.get(ts)
        interval_s = (l or s).interval_s
        net = (l.energy.kwh if l else 0.0) - (s.energy.kwh if s else 0.0)
        grid.add_import(IntervalReading(ts, interval_s, EnergyQuantity.of(max(0.0, net))))
        grid.add_export(IntervalReading(ts, interval_s, EnergyQuantity.of(max(0.0, -net))))
    return grid
