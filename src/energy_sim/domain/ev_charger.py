"""EVCharger — the car charger (Zappi) as a device, with its OWN measured solar/grid split.

The split (diverted vs boosted) is whatever the device metered, carried verbatim; it is never
reconstructed from whole-home grid flows. Those come from a separate, lower-reading meter, so
differencing them attributes household grid draw to the car and over-counts its grid use. The
Zappi measured what went into the car directly — we trust that.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from energy_sim.domain.device import Device, DeviceRole


@dataclass(frozen=True)
class EVChargeInterval:
    """Energy delivered to the car over one interval, split by source as the device measured it."""

    ts_utc: datetime
    interval_s: int
    solar_kwh: float
    grid_kwh: float

    def __post_init__(self) -> None:
        if self.ts_utc.tzinfo is None:
            raise ValueError("EVChargeInterval.ts_utc must be timezone-aware (UTC)")
        if self.solar_kwh < 0 or self.grid_kwh < 0:
            raise ValueError("EVChargeInterval energy must be non-negative")

    @property
    def total_kwh(self) -> float:
        return self.solar_kwh + self.grid_kwh


class EVCharger(Device):
    """The EV charger device. Records charging intervals; reports them sorted by time."""

    def __init__(self, name: str) -> None:
        super().__init__(name, DeviceRole.EV_CHARGER)
        self._intervals: dict[datetime, EVChargeInterval] = {}

    def add_charge(self, interval: EVChargeInterval) -> None:
        self._intervals[interval.ts_utc] = interval

    def intervals(self) -> list[EVChargeInterval]:
        return [self._intervals[ts] for ts in sorted(self._intervals)]
