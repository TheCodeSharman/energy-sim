"""Battery — an energy store in the topology (a Device, but not a meter).

Unlike metered devices it records no readings; it transforms flows. A dispatch policy offers it
surplus (``charge``) and asks it to meet deficits (``discharge``); each call returns the energy
actually moved, clamped by the power rating over the interval and by the state of charge against
usable capacity.

Round-trip loss is split sqrt each way (``charge`` and ``discharge`` each keep ``sqrt(rt)``), so a
full store-and-release loop keeps exactly ``round_trip_efficiency`` of the energy. SoC is held in
stored-energy terms (DC side); charge/discharge figures are terminal (AC side) energies.
"""
from __future__ import annotations

from energy_sim.domain.device import Device, DeviceRole


class Battery(Device):
    def __init__(
        self,
        name: str,
        usable_kwh: float,
        max_power_kw: float,
        round_trip_efficiency: float,
        initial_soc_kwh: float = 0.0,
    ) -> None:
        super().__init__(name, DeviceRole.BATTERY)
        if usable_kwh <= 0:
            raise ValueError("usable_kwh must be positive")
        if max_power_kw <= 0:
            raise ValueError("max_power_kw must be positive")
        if not 0 < round_trip_efficiency <= 1:
            raise ValueError("round_trip_efficiency must be in (0, 1]")
        if not 0 <= initial_soc_kwh <= usable_kwh:
            raise ValueError("initial_soc_kwh must be within [0, usable_kwh]")
        self.usable_kwh = usable_kwh
        self.max_power_kw = max_power_kw
        self._one_way_efficiency = round_trip_efficiency ** 0.5
        self._soc_kwh = initial_soc_kwh

    @property
    def soc_kwh(self) -> float:
        return self._soc_kwh

    def _power_cap_kwh(self, interval_s: int) -> float:
        return self.max_power_kw * interval_s / 3600.0

    def charge(self, offered_kwh: float, interval_s: int) -> float:
        """Take as much of ``offered_kwh`` as power and remaining capacity allow; return it."""
        eff = self._one_way_efficiency
        room_at_terminal = (self.usable_kwh - self._soc_kwh) / eff
        accepted = min(offered_kwh, self._power_cap_kwh(interval_s), room_at_terminal)
        self._soc_kwh += accepted * eff
        return accepted

    def discharge(self, requested_kwh: float, interval_s: int) -> float:
        """Meet as much of ``requested_kwh`` as power and stored energy allow; return it."""
        eff = self._one_way_efficiency
        available_at_terminal = self._soc_kwh * eff
        delivered = min(requested_kwh, self._power_cap_kwh(interval_s), available_at_terminal)
        self._soc_kwh -= delivered / eff
        return delivered
