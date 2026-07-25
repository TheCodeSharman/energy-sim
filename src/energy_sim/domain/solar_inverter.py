"""SolarInverter — PV generation. Represented in iteration 1 (energy-balance check +
future use) but carries no economics yet."""
from __future__ import annotations

from energy_sim.domain.device import DeviceRole, SingleMeterDevice


class SolarInverter(SingleMeterDevice):
    def __init__(self, name: str) -> None:
        super().__init__(name, DeviceRole.SOLAR)
