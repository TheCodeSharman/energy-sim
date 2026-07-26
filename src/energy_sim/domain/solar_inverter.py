"""SolarInverter — PV generation.

Does not drive cost; only the grid connection does. Present so the energy identity
`consumption = solar + import - export` can be asserted as a data-quality check.
"""
from __future__ import annotations

from energy_sim.domain.device import DeviceRole, SingleMeterDevice


class SolarInverter(SingleMeterDevice):
    def __init__(self, name: str) -> None:
        super().__init__(name, DeviceRole.SOLAR)
