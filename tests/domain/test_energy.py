"""EnergyQuantity value object: kWh amounts and the W->kWh interval conversion."""
import pytest

from energy_sim.domain.energy import EnergyQuantity


def test_of_exposes_kwh():
    assert EnergyQuantity.of(2.5).kwh == 2.5


def test_zero():
    assert EnergyQuantity.zero().kwh == 0


def test_addition():
    assert EnergyQuantity.of(1.5) + EnergyQuantity.of(2.0) == EnergyQuantity.of(3.5)


def test_equality_by_value():
    assert EnergyQuantity.of(1.0) == EnergyQuantity.of(1.0)
    assert EnergyQuantity.of(1.0) != EnergyQuantity.of(1.1)


def test_from_average_watts_over_one_hour():
    # 2000 W sustained for 3600 s == 2.0 kWh
    assert EnergyQuantity.from_average_watts(2000, 3600).kwh == pytest.approx(2.0)


def test_from_average_watts_over_five_minutes():
    # 1200 W for 300 s == 1200 * 300 / 3600 / 1000 == 0.1 kWh
    assert EnergyQuantity.from_average_watts(1200, 300).kwh == pytest.approx(0.1)
