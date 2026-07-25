"""Device — base entity in the home-energy topology, plus the role enum.

A ``Device`` has identity (a name) and a role. ``SingleMeterDevice`` is the common case:
one metered channel recording a series of ``IntervalReading``. ``GridConnection`` is the
dual-channel exception (import + export) and lives in its own module.
"""
from __future__ import annotations

from enum import Enum

from energy_sim.domain.reading import IntervalReading


class DeviceRole(Enum):
    GRID = "grid"
    SOLAR = "solar"
    LOAD = "load"


class Device:
    """An identified device with a role in the energy topology."""

    def __init__(self, name: str, role: DeviceRole) -> None:
        self.name = name
        self.role = role


class SingleMeterDevice(Device):
    """A device whose meter records one channel of energy readings."""

    def __init__(self, name: str, role: DeviceRole) -> None:
        super().__init__(name, role)
        self._readings: list[IntervalReading] = []

    def add_reading(self, reading: IntervalReading) -> None:
        self._readings.append(reading)

    @property
    def readings(self) -> tuple[IntervalReading, ...]:
        return tuple(sorted(self._readings, key=lambda r: r.ts_utc))
