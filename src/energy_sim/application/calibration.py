"""CT calibration — removing the household metering bias before judging the rate model.

The `pf:*` power flows come from household current transformers, which read ~7-16% low
against Aurora's revenue meter. That bias would otherwise dominate the modelled-vs-billed
dollar gap and hide whatever error belongs to the rate model itself.

So we derive a scalar per direction straight from Aurora's own metered kWh:

    import_factor = Aurora metered import kWh / pf:* import kWh
    export_factor = Aurora metered export kWh / pf:* export kWh

and re-cost a Site whose grid flows have been scaled by them. The residual that survives is
rate/classifier/model error, with metering bias taken out.

Import and export are scaled independently: they are different CT paths and are not observed
to drift by the same amount. Solar and load carry through unscaled — they are metered by
other CTs that Aurora gives us no ground truth for.
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
