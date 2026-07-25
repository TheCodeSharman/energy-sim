"""Money value object: exact currency arithmetic, no float drift."""
from decimal import Decimal

from energy_sim.domain.money import Money


def test_cents_formats_as_dollars():
    assert str(Money.from_cents(150)) == "$1.50"


def test_dollars_constructor_matches_cents():
    assert Money.from_dollars("1.50") == Money.from_cents(150)


def test_zero_is_zero():
    assert str(Money.zero()) == "$0.00"


def test_addition():
    assert Money.from_cents(150) + Money.from_cents(50) == Money.from_cents(200)


def test_subtraction():
    assert Money.from_cents(200) - Money.from_cents(50) == Money.from_cents(150)


def test_multiplication_by_scalar():
    assert Money.from_cents(100) * 3 == Money.from_cents(300)


def test_fractional_cents_are_preserved_until_formatting():
    # rate (c/kWh) x energy (kWh) yields fractional cents; they must not be lost.
    exact = Money.from_cents(Decimal("14.876") * Decimal("0.5"))  # 7.438c
    assert exact.cents == Decimal("7.438")
    # formatting rounds half-up to whole cents for display
    assert str(exact) == "$0.07"


def test_negative_formats_with_leading_minus():
    assert str(Money.from_cents(-150)) == "-$1.50"


def test_equality_is_by_value():
    assert Money.from_cents(100) == Money.from_cents(100)
    assert Money.from_cents(100) != Money.from_cents(101)
