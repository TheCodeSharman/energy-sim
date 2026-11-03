"""SelfConsumptionDispatch — turn real grid flows into a battery-adjusted series.

The simplest, most common home-battery policy: store surplus that would otherwise be exported,
and spend it to cover import. It walks the GridConnection in time order (so a morning charge is
available for an evening deficit), offering each interval's export to the battery and asking it
to meet each interval's import, then emits a new Site whose GridConnection carries the adjusted
flows. Costing is unchanged — CostCalculatorService re-runs over the new Site, which is the whole
point of keeping the battery out of the cost seam.
"""
from __future__ import annotations

from energy_sim.domain.battery import Battery
from energy_sim.domain.energy import EnergyQuantity
from energy_sim.domain.grid_connection import GridConnection
from energy_sim.domain.reading import IntervalReading
from energy_sim.domain.site import Site


class SelfConsumptionDispatch:
    def apply(self, site: Site, battery: Battery) -> Site:
        adjusted = GridConnection(name=site.grid.name)
        for gi in site.grid.intervals():
            export_kwh = gi.export_energy.kwh
            import_kwh = gi.import_energy.kwh
            if export_kwh > 0:
                export_kwh -= battery.charge(export_kwh, gi.interval_s)
            if import_kwh > 0:
                import_kwh -= battery.discharge(import_kwh, gi.interval_s)
            adjusted.add_import(
                IntervalReading(gi.ts_utc, gi.interval_s, EnergyQuantity.of(import_kwh)))
            adjusted.add_export(
                IntervalReading(gi.ts_utc, gi.interval_s, EnergyQuantity.of(export_kwh)))
        return Site(name=site.name, grid=adjusted, solar=site.solar, load=site.load)
