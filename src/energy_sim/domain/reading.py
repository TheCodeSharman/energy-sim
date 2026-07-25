"""IntervalReading — an energy reading over a bounded, timestamped interval.

Resolution-agnostic: the reading carries its own ``interval_s`` (300, 3600, ...) and is
already energy (kWh), so nothing downstream needs to know the sampling resolution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from energy_sim.domain.energy import EnergyQuantity


@dataclass(frozen=True)
class IntervalReading:
    """Energy recorded over ``[ts_utc, ts_utc + interval_s)``. Compared by value."""

    ts_utc: datetime
    interval_s: int
    energy: EnergyQuantity

    def __post_init__(self) -> None:
        if self.ts_utc.tzinfo is None:
            raise ValueError("IntervalReading.ts_utc must be timezone-aware (UTC)")

    @property
    def end_utc(self) -> datetime:
        return self.ts_utc + timedelta(seconds=self.interval_s)
