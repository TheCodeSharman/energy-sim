"""CSV snapshot store: persist a period's flows once, then compute/validate offline.

A committed snapshot makes runs reproducible (the AI-codegen-experiment goal). Grid
import/export drive cost; solar/consumption enable the energy-balance check; the Aurora
columns are the billed ground truth for validation (hourly-only, so blank on sub-hour rows).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from energy_sim.domain.energy import EnergyQuantity
from energy_sim.domain.grid_connection import GridConnection
from energy_sim.domain.house_load import HouseLoad
from energy_sim.domain.reading import IntervalReading
from energy_sim.domain.site import Site
from energy_sim.domain.solar_inverter import SolarInverter

COLUMNS = [
    "timestamp_utc", "interval_s", "grid_import_kwh", "grid_export_kwh",
    "solar_kwh", "consumption_kwh",
    "aurora_kwh_peak", "aurora_kwh_offpeak", "aurora_kwh_export",
    "aurora_dollar_peak", "aurora_dollar_offpeak", "aurora_dollar_export",
    "aurora_dollar_supply", "aurora_dollar_total",
]


@dataclass(frozen=True)
class SnapshotRow:
    ts_utc: datetime
    interval_s: int
    # All four flows are optional: a blank means the source had no reading for this interval,
    # which is not the same claim as "zero". Cost treats a blank as no energy, but only after
    # the row has said, honestly, that nothing was measured. See ``incomplete_rows``.
    grid_import_kwh: float | None
    grid_export_kwh: float | None
    solar_kwh: float | None
    consumption_kwh: float | None
    # Aurora kWh are hourly (peak/off-peak/export). Aurora dollars are DAILY totals placed on
    # the day's start row (Aurora bills dollars per day, not per hour); blank on other rows.
    aurora_kwh_peak: float | None
    aurora_kwh_offpeak: float | None
    aurora_kwh_export: float | None
    # Dollars are Decimal, never float: they are exact amounts, not measurements. kWh above
    # stay float because they ARE measurements — a watt average carries no exact decimal.
    aurora_dollar_peak: Decimal | None
    aurora_dollar_offpeak: Decimal | None
    aurora_dollar_export: Decimal | None
    aurora_dollar_supply: Decimal | None = None   # daily "Other" (fixed supply charge)
    aurora_dollar_total: Decimal | None = None    # daily all-in billed total


def _fmt(value: float | Decimal | None) -> str:
    # repr() for floats so the value round-trips exactly; Decimals print as written.
    return "" if value is None else (str(value) if isinstance(value, Decimal) else repr(value))


def _num(cell: str) -> float | None:
    return None if cell == "" else float(cell)


def _money(cell: str) -> Decimal | None:
    """Dollars are read straight from the CSV text, so no float ever touches them."""
    return None if cell == "" else Decimal(cell)


def write_snapshot(path: str | Path, rows: list[SnapshotRow]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for r in rows:
            writer.writerow([
                r.ts_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                r.interval_s, _fmt(r.grid_import_kwh), _fmt(r.grid_export_kwh),
                _fmt(r.solar_kwh), _fmt(r.consumption_kwh),
                _fmt(r.aurora_kwh_peak), _fmt(r.aurora_kwh_offpeak), _fmt(r.aurora_kwh_export),
                _fmt(r.aurora_dollar_peak), _fmt(r.aurora_dollar_offpeak), _fmt(r.aurora_dollar_export),
                _fmt(r.aurora_dollar_supply), _fmt(r.aurora_dollar_total),
            ])


def read_snapshot(path: str | Path) -> "Snapshot":
    rows = []
    with open(path, newline="") as f:
        for rec in csv.DictReader(f):
            rows.append(SnapshotRow(
                ts_utc=datetime.strptime(rec["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc),
                interval_s=int(rec["interval_s"]),
                grid_import_kwh=_num(rec["grid_import_kwh"]),
                grid_export_kwh=_num(rec["grid_export_kwh"]),
                solar_kwh=_num(rec["solar_kwh"]),
                consumption_kwh=_num(rec["consumption_kwh"]),
                aurora_kwh_peak=_num(rec["aurora_kwh_peak"]),
                aurora_kwh_offpeak=_num(rec["aurora_kwh_offpeak"]),
                aurora_kwh_export=_num(rec["aurora_kwh_export"]),
                aurora_dollar_peak=_money(rec["aurora_dollar_peak"]),
                aurora_dollar_offpeak=_money(rec["aurora_dollar_offpeak"]),
                aurora_dollar_export=_money(rec["aurora_dollar_export"]),
                aurora_dollar_supply=_money(rec.get("aurora_dollar_supply", "")),
                aurora_dollar_total=_money(rec.get("aurora_dollar_total", "")),
            ))
    return Snapshot(rows)


class Snapshot:
    """A parsed CSV snapshot: the sim's raw material for a period."""

    def __init__(self, rows: list[SnapshotRow]) -> None:
        self.rows = rows

    _AURORA_FIELDS = (
        "aurora_kwh_peak", "aurora_kwh_offpeak", "aurora_kwh_export",
        "aurora_dollar_peak", "aurora_dollar_offpeak", "aurora_dollar_export",
        "aurora_dollar_supply", "aurora_dollar_total",
    )

    @property
    def has_aurora(self) -> bool:
        return any(self._row_has_aurora(r) for r in self.rows)

    def _row_has_aurora(self, row: SnapshotRow) -> bool:
        return any(getattr(row, f) is not None for f in self._AURORA_FIELDS)

    def aurora_rows(self) -> list[SnapshotRow]:
        return [r for r in self.rows if self._row_has_aurora(r)]

    def _has_solar_load(self) -> bool:
        return any(r.solar_kwh is not None and r.consumption_kwh is not None for r in self.rows)

    _FLOW_FIELDS = ("grid_import_kwh", "grid_export_kwh", "solar_kwh", "consumption_kwh")

    def incomplete_rows(self) -> list[SnapshotRow]:
        """Rows where at least one flow was measured and at least one was not.

        These are intervals assembled from partial source coverage. They are not an error —
        the sources really do have holes — but any total over them is short by an unknown
        amount, so the number of them belongs in the output rather than in a comment.
        """
        return [r for r in self.rows if self._is_incomplete(r)]

    def _is_incomplete(self, row: SnapshotRow) -> bool:
        present = [getattr(row, f) is not None for f in self._FLOW_FIELDS]
        return any(present) and not all(present)

    def to_site(self, name: str = "Home") -> Site:
        grid = GridConnection(name="Aurora meter")
        for r in self.rows:
            # An unmeasured interval contributes no energy: we cannot bill for a reading that
            # does not exist. ``incomplete_rows`` is how that shows up in the output.
            grid.add_import(_reading(r.ts_utc, r.interval_s, r.grid_import_kwh or 0.0))
            grid.add_export(_reading(r.ts_utc, r.interval_s, r.grid_export_kwh or 0.0))

        solar = load = None
        if self._has_solar_load():
            solar = SolarInverter(name="Sungrow")
            load = HouseLoad(name="House")
            for r in self.rows:
                solar.add_reading(_reading(r.ts_utc, r.interval_s, r.solar_kwh or 0.0))
                load.add_reading(_reading(r.ts_utc, r.interval_s, r.consumption_kwh or 0.0))

        return Site(name=name, grid=grid, solar=solar, load=load)

    def aurora_kwh_totals(self) -> tuple[float, float, float]:
        """(peak, offpeak, export) kWh summed over the period."""
        return (
            self._sum("aurora_kwh_peak"),
            self._sum("aurora_kwh_offpeak"),
            self._sum("aurora_kwh_export"),
        )

    def aurora_dollar_totals(self) -> tuple[Decimal, Decimal, Decimal]:
        """(peak, offpeak, export) dollars summed over the period, signs as billed."""
        return (
            self._sum_money("aurora_dollar_peak"),
            self._sum_money("aurora_dollar_offpeak"),
            self._sum_money("aurora_dollar_export"),
        )

    def aurora_supply_total(self) -> Decimal:
        """Aurora's billed fixed supply charge over the period (daily 'Other', summed)."""
        return self._sum_money("aurora_dollar_supply")

    def aurora_billed_total(self) -> Decimal:
        """Aurora's all-in billed total over the period (daily 'Total', summed) — the target."""
        return self._sum_money("aurora_dollar_total")

    def aurora_import_kwh_total(self) -> float:
        return self._sum("aurora_kwh_peak") + self._sum("aurora_kwh_offpeak")

    def aurora_export_kwh_total(self) -> float:
        return self._sum("aurora_kwh_export")

    def pf_import_kwh_total(self) -> float:
        return self._sum("grid_import_kwh")

    def pf_export_kwh_total(self) -> float:
        return self._sum("grid_export_kwh")

    def _sum(self, field_name: str) -> float:
        return sum(getattr(r, field_name) or 0.0 for r in self.rows)

    def _sum_money(self, field_name: str) -> Decimal:
        """Summed as Decimal end to end — money is never accumulated as float."""
        return sum((getattr(r, field_name) or Decimal(0) for r in self.rows), Decimal(0))


def _reading(ts, interval_s, kwh) -> IntervalReading:
    return IntervalReading(ts_utc=ts, interval_s=interval_s, energy=EnergyQuantity.of(kwh))
