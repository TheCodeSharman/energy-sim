"""EnergyQuantity — a quantity of energy in kilowatt-hours."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnergyQuantity:
    """An amount of energy, in kWh. Immutable, compared by value."""

    kwh: float

    @classmethod
    def zero(cls) -> "EnergyQuantity":
        return cls(0.0)

    @classmethod
    def of(cls, kwh: float) -> "EnergyQuantity":
        return cls(float(kwh))

    @classmethod
    def from_average_watts(cls, watts: float, seconds: float) -> "EnergyQuantity":
        """Energy from an average power sustained over an interval.

        kWh = W x s / 3600 (s/h) / 1000 (W/kW). This is how the exporter turns a
        `pf:*_w` average-over-interval into per-interval energy at any resolution.
        """
        return cls(watts * seconds / 3600.0 / 1000.0)

    def __add__(self, other: "EnergyQuantity") -> "EnergyQuantity":
        return EnergyQuantity(self.kwh + other.kwh)
