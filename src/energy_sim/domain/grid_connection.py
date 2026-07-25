"""GridConnection — the metered grid connection point (import + export channels).

The only device that drives cost in iteration 1. The Aurora smart meter is the billed
ground truth for this device. Import and export are separate measured channels (both >=0;
a single interval can carry both), aligned by timestamp into ``GridInterval`` records.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from energy_sim.domain.device import Device, DeviceRole
from energy_sim.domain.energy import EnergyQuantity
from energy_sim.domain.reading import IntervalReading


@dataclass(frozen=True)
class GridInterval:
    """Import and export energy over one interval at the grid connection."""

    ts_utc: datetime
    interval_s: int
    import_energy: EnergyQuantity
    export_energy: EnergyQuantity


class GridConnection(Device):
    def __init__(self, name: str) -> None:
        super().__init__(name, DeviceRole.GRID)
        self._imports: dict[datetime, IntervalReading] = {}
        self._exports: dict[datetime, IntervalReading] = {}

    def add_import(self, reading: IntervalReading) -> None:
        self._imports[reading.ts_utc] = reading

    def add_export(self, reading: IntervalReading) -> None:
        self._exports[reading.ts_utc] = reading

    def intervals(self) -> list[GridInterval]:
        """Import/export aligned by timestamp, sorted; a missing channel reads as zero."""
        timestamps = sorted(self._imports.keys() | self._exports.keys())
        result = []
        for ts in timestamps:
            imp = self._imports.get(ts)
            exp = self._exports.get(ts)
            interval_s = (imp or exp).interval_s
            result.append(
                GridInterval(
                    ts_utc=ts,
                    interval_s=interval_s,
                    import_energy=imp.energy if imp else EnergyQuantity.zero(),
                    export_energy=exp.energy if exp else EnergyQuantity.zero(),
                )
            )
        return result
