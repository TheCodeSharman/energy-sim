"""Battery device: charge/discharge physics — capacity, power, round-trip efficiency, SoC.

The battery is a store, not a meter: charge() accepts offered surplus and returns how much it
took; discharge() meets a requested deficit and returns how much it delivered. Both are clamped
by the power rating (over the interval) and the capacity. Round-trip loss is split sqrt each
way, so a full store-and-release loop keeps `round_trip_efficiency` of the energy.
"""
from energy_sim.domain.battery import Battery
from energy_sim.domain.device import DeviceRole


def _battery(usable=10.0, power=5.0, round_trip=1.0, soc=0.0):
    return Battery(name="Sungrow SBH", usable_kwh=usable, max_power_kw=power,
                   round_trip_efficiency=round_trip, initial_soc_kwh=soc)


def test_battery_has_battery_role():
    assert _battery().role is DeviceRole.BATTERY


def test_charging_lossless_battery_stores_offered_energy():
    b = _battery(round_trip=1.0)
    accepted = b.charge(offered_kwh=2.0, interval_s=3600)
    assert accepted == 2.0
    assert b.soc_kwh == 2.0


def test_charge_is_clamped_by_power_over_the_interval():
    b = _battery(power=5.0, round_trip=1.0)  # 5 kW over 1 h = 5 kWh max
    assert b.charge(offered_kwh=8.0, interval_s=3600) == 5.0


def test_charge_power_cap_scales_with_interval_length():
    b = _battery(power=5.0, round_trip=1.0)  # 5 kW over 30 min = 2.5 kWh max
    assert b.charge(offered_kwh=8.0, interval_s=1800) == 2.5


def test_charge_is_clamped_by_remaining_capacity():
    b = _battery(usable=10.0, power=100.0, round_trip=1.0, soc=9.0)
    assert b.charge(offered_kwh=5.0, interval_s=3600) == 1.0
    assert b.soc_kwh == 10.0


def test_round_trip_efficiency_split_sqrt_each_way():
    # rt=0.81 -> one-way sqrt = 0.9. Charge 10 (power/capacity generous) stores 9.0...
    b = _battery(usable=100.0, power=100.0, round_trip=0.81)
    b.charge(offered_kwh=10.0, interval_s=3600)
    assert b.soc_kwh == 9.0
    # ...and fully discharging delivers 9.0 * 0.9 = 8.1 (90% of 90% = 81% round trip).
    assert b.discharge(requested_kwh=100.0, interval_s=3600) == 8.1


def test_discharge_is_clamped_by_power_and_meets_smaller_requests():
    b = _battery(power=5.0, round_trip=1.0, soc=8.0)
    assert b.discharge(requested_kwh=2.0, interval_s=3600) == 2.0   # request smaller than power
    assert b.discharge(requested_kwh=9.0, interval_s=3600) == 5.0   # clamped to 5 kW


def test_discharge_from_empty_delivers_nothing():
    assert _battery(soc=0.0).discharge(requested_kwh=3.0, interval_s=3600) == 0.0


def test_rejects_nonsensical_configuration():
    import pytest
    with pytest.raises(ValueError):
        _battery(usable=-1.0)
    with pytest.raises(ValueError):
        _battery(round_trip=1.5)
    with pytest.raises(ValueError):
        _battery(soc=20.0)  # soc above usable
