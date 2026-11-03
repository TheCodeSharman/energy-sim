"""EVCharger device: records the car's charging with the Zappi's OWN measured solar/grid split.

The split is read straight off the device (diverted vs boosted), never reconstructed from
whole-home grid data — those are a different, lower-reading meter, so subtracting them
over-attributes household grid to the car. Total is solar + grid by construction.
"""
from datetime import datetime, timezone

import pytest

from energy_sim.domain.device import DeviceRole
from energy_sim.domain.ev_charger import EVCharger, EVChargeInterval

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 6, 1, 1, 0, tzinfo=UTC)


def _ci(ts, solar, grid):
    return EVChargeInterval(ts_utc=ts, interval_s=3600, solar_kwh=solar, grid_kwh=grid)


def test_ev_charger_has_its_role():
    assert EVCharger(name="Zappi").role is DeviceRole.EV_CHARGER


def test_total_is_solar_plus_grid():
    assert _ci(T0, 2.0, 0.5).total_kwh == 2.5


def test_intervals_returned_sorted_by_time():
    ev = EVCharger(name="Zappi")
    ev.add_charge(_ci(T1, 1.0, 0.0))
    ev.add_charge(_ci(T0, 0.0, 1.0))
    assert [c.ts_utc for c in ev.intervals()] == [T0, T1]


def test_charge_interval_rejects_negative_energy():
    with pytest.raises(ValueError):
        _ci(T0, -1.0, 0.0)


def test_charge_interval_requires_utc():
    with pytest.raises(ValueError):
        EVChargeInterval(ts_utc=datetime(2026, 6, 1, 0, 0), interval_s=3600,
                         solar_kwh=1.0, grid_kwh=0.0)
