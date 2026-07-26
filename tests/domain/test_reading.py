"""IntervalReading value object: an energy reading over a bounded time interval."""
from datetime import datetime, timedelta, timezone

import pytest

from energy_sim.domain.energy import EnergyQuantity
from energy_sim.domain.reading import IntervalReading

UTC = timezone.utc


def test_holds_timestamp_interval_and_energy():
    ts = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    r = IntervalReading(ts_utc=ts, interval_s=3600, energy=EnergyQuantity.of(0.5))
    assert r.ts_utc == ts
    assert r.interval_s == 3600
    assert r.energy == EnergyQuantity.of(0.5)


def test_end_utc_is_start_plus_interval():
    ts = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    r = IntervalReading(ts_utc=ts, interval_s=3600, energy=EnergyQuantity.of(0.5))
    assert r.end_utc == ts + timedelta(seconds=3600)


def test_rejects_naive_timestamp():
    naive = datetime(2026, 6, 1, 0, 0)  # no tzinfo
    with pytest.raises(ValueError):
        IntervalReading(ts_utc=naive, interval_s=3600, energy=EnergyQuantity.of(0.5))


def test_equality_by_value():
    ts = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    a = IntervalReading(ts_utc=ts, interval_s=3600, energy=EnergyQuantity.of(0.5))
    b = IntervalReading(ts_utc=ts, interval_s=3600, energy=EnergyQuantity.of(0.5))
    assert a == b
