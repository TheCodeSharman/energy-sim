"""CT calibration — removing household metering bias before judging the rate model.

The `pf:*` flows come from household CTs, which read low against Aurora's revenue meter.
Scaling them onto Aurora's metered kWh separates metering error from rate-model error, so
the validation report can show both. Import and export scale independently (different CT
paths); solar and load are untouched, as Aurora gives no ground truth for them.
"""
from __future__ import annotations

from dataclasses import dataclass

from energy_sim.domain.energy import EnergyQuantity
from energy_sim.domain.grid_connection import GridConnection
from energy_sim.domain.reading import IntervalReading
from energy_sim.domain.site import Site
from energy_sim.infrastructure.csv_store import Snapshot


@dataclass(frozen=True)
class CalibrationFactors:
    """Multipliers taking pf:* grid energy onto Aurora's metered scale (1.0 = no bias)."""

    import_factor: float
    export_factor: float


def calibration_factors(snapshot: Snapshot) -> CalibrationFactors:
    return CalibrationFactors(
        import_factor=_ratio(snapshot.aurora_import_kwh_total(), snapshot.pf_import_kwh_total()),
        export_factor=_ratio(snapshot.aurora_export_kwh_total(), snapshot.pf_export_kwh_total()),
    )


def calibrate(site: Site, import_factor: float, export_factor: float) -> Site:
    """A copy of ``site`` with its grid import/export scaled; the original is left alone."""
    grid = GridConnection(name=site.grid.name)
    for gi in site.grid.intervals():
        grid.add_import(_scaled(gi.ts_utc, gi.interval_s, gi.import_energy, import_factor))
        grid.add_export(_scaled(gi.ts_utc, gi.interval_s, gi.export_energy, export_factor))
    return Site(name=site.name, grid=grid, solar=site.solar, load=site.load)


def _scaled(ts_utc, interval_s: int, energy: EnergyQuantity, factor: float) -> IntervalReading:
    return IntervalReading(
        ts_utc=ts_utc, interval_s=interval_s, energy=EnergyQuantity.of(energy.kwh * factor)
    )


def _ratio(aurora_kwh: float, pf_kwh: float) -> float:
    """Unity when there is no pf:* energy to scale, or no Aurora reading to scale it to."""
    if pf_kwh == 0 or aurora_kwh == 0:
        return 1.0
    return aurora_kwh / pf_kwh
