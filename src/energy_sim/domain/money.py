"""Money — an exact-arithmetic currency value object.

Backed by ``Decimal`` cents rather than ``int`` cents: rate (c/kWh) times energy (kWh)
produces *fractional* cents, and rounding each interval to a whole cent would accumulate
error across a month. We keep cents exact and round half-up to whole cents only for display.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Union

Numeric = Union[int, float, str, Decimal]


def _to_decimal(value: Numeric) -> Decimal:
    # str() around float avoids binary-float artefacts (e.g. 0.1 -> 0.1000000000000000055).
    return value if isinstance(value, Decimal) else Decimal(str(value))


class Money:
    """A monetary amount, stored exactly as a ``Decimal`` number of cents."""

    __slots__ = ("_cents",)

    def __init__(self, cents: Decimal) -> None:
        self._cents = cents

    @classmethod
    def zero(cls) -> "Money":
        return cls(Decimal(0))

    @classmethod
    def from_cents(cls, value: Numeric) -> "Money":
        return cls(_to_decimal(value))

    @classmethod
    def from_dollars(cls, value: Numeric) -> "Money":
        return cls(_to_decimal(value) * 100)

    @property
    def cents(self) -> Decimal:
        return self._cents

    @property
    def dollars(self) -> Decimal:
        return self._cents / 100

    def __add__(self, other: "Money") -> "Money":
        return Money(self._cents + other._cents)

    def __sub__(self, other: "Money") -> "Money":
        return Money(self._cents - other._cents)

    def __mul__(self, scalar: Numeric) -> "Money":
        return Money(self._cents * _to_decimal(scalar))

    __rmul__ = __mul__

    def __neg__(self) -> "Money":
        return Money(-self._cents)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self._cents == other._cents

    def __hash__(self) -> int:
        return hash(self._cents)

    def __str__(self) -> str:
        whole_cents = self._cents.quantize(Decimal(1), rounding=ROUND_HALF_UP)
        sign = "-" if whole_cents < 0 else ""
        dollars = abs(whole_cents) / 100
        return f"{sign}${dollars:.2f}"

    def __repr__(self) -> str:
        return f"Money.from_cents({self._cents})"
