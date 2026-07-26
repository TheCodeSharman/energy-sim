"""Site — the aggregate root owning the device topology.

Holds the GridConnection (drives cost) plus the optional SolarInverter and HouseLoad, and
can assert the energy identity `consumption = solar + grid_import - grid_export` per interval.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from energy_sim.domain.grid_connection import GridConnection
from energy_sim.domain.house_load import HouseLoad
from energy_sim.domain.solar_inverter import SolarInverter


@dataclass(frozen=True)
class BalanceError:
    """An interval where the energy identity does not hold within tolerance."""

    ts_utc: datetime
    discrepancy_kwh: float


class Site:
    def __init__(
        self,
        name: str,
        grid: GridConnection,
        solar: SolarInverter | None = None,
        load: HouseLoad | None = None,
    ) -> None:
        self.name = name
        self.grid = grid
        self.solar = solar
        self.load = load

    def energy_balance_errors(self, tolerance_kwh: float) -> list[BalanceError]:
        """Intervals violating `consumption = solar + import - export`.

        Returns [] if solar or load is absent (identity cannot be asserted).
        """
        if self.solar is None or self.load is None:
            return []

        solar_by_ts = {r.ts_utc: r.energy.kwh for r in self.solar.readings}
        load_by_ts = {r.ts_utc: r.energy.kwh for r in self.load.readings}

        errors = []
        for gi in self.grid.intervals():
            solar = solar_by_ts.get(gi.ts_utc, 0.0)
            consumption = load_by_ts.get(gi.ts_utc, 0.0)
            expected = solar + gi.import_energy.kwh - gi.export_energy.kwh
            discrepancy = consumption - expected
            if abs(discrepancy) > tolerance_kwh:
                errors.append(BalanceError(ts_utc=gi.ts_utc, discrepancy_kwh=discrepancy))
        return errors
