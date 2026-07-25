"""HouseLoad — whole-home consumption. Represented in iteration 1 (energy-balance check +
future use) but carries no economics yet. Note: consumption already includes EV charging
from ~2025-07 (see HomeAssistantConfig CHANGELOG)."""
from __future__ import annotations

from energy_sim.domain.device import DeviceRole, SingleMeterDevice


class HouseLoad(SingleMeterDevice):
    def __init__(self, name: str) -> None:
        super().__init__(name, DeviceRole.LOAD)
