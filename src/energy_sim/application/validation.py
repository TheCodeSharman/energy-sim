"""ValidationService — does the modelled cost match the Aurora bill?

Reports three things, most-isolated first, so a discrepancy can be attributed:
  1. rate legs — Aurora's own metered kWh x our rates vs its billed dollars (no CT or
     classifier error in the way)
  2. peak-window classifier — our is_peak(ts) vs which tariff Aurora billed each hour to
  3. end-to-end dollars — modelled net cost from the pf:* flows vs the billed total, both
     as measured and after CT calibration

kWh are hourly and dollars are daily, so both are summed over the period before comparing.
See docs/aurora-data.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from energy_sim.application.calibration import (
    CalibrationFactors,
    calibrate,
    calibration_factors,
)
from energy_sim.application.cost_calculator import CostCalculatorService
from energy_sim.domain.money import Money
from energy_sim.domain.tariff import Tariff
from energy_sim.infrastructure.csv_store import Snapshot


@dataclass(frozen=True)
class LineComparison:
    label: str
    modelled: Money
    actual: Money

    @property
    def delta(self) -> Money:
        return self.modelled - self.actual

    @property
    def delta_pct(self) -> float | None:
        actual = float(self.actual.dollars)
        if actual == 0:
            return None
        return float(self.delta.dollars) / actual * 100.0

    def within(self, tolerance_cents: Decimal | float) -> bool:
        return abs(self.delta.cents) <= Money.from_cents(tolerance_cents).cents


@dataclass(frozen=True)
class ClassifierResult:
    agreements: int
    disagreements: int
    mismatched_hours: list[datetime]


@dataclass(frozen=True)
class ValidationReport:
    has_aurora: bool
    rate_checks: list[LineComparison]
    classifier: ClassifierResult
    end_to_end: LineComparison | None
    calibration: CalibrationFactors | None = None
    end_to_end_calibrated: LineComparison | None = None


class ValidationService:
    def validate(self, snapshot: Snapshot, tariff: Tariff) -> ValidationReport:
        if not snapshot.has_aurora:
            return ValidationReport(
                has_aurora=False, rate_checks=[],
                classifier=ClassifierResult(0, 0, []), end_to_end=None,
            )
        aurora_rows = snapshot.aurora_rows()
        factors = calibration_factors(snapshot)
        return ValidationReport(
            has_aurora=True,
            rate_checks=self._rate_checks(aurora_rows, tariff),
            classifier=self._classifier_check(aurora_rows, tariff),
            end_to_end=self._end_to_end(snapshot, tariff, "net vs bill (pf:* as measured)"),
            calibration=factors,
            end_to_end_calibrated=self._end_to_end(
                snapshot, tariff, "net vs bill (CT-calibrated)", factors,
            ),
        )

    def _rate_checks(self, rows, tariff: Tariff) -> list[LineComparison]:
        modelled_peak = modelled_offpeak = modelled_export = modelled_supply = Money.zero()
        for r in rows:
            ts = r.ts_utc
            modelled_peak += Money.from_cents(tariff.peak_rate(ts)) * _z(r.aurora_kwh_peak)
            modelled_offpeak += Money.from_cents(tariff.offpeak_rate(ts)) * _z(r.aurora_kwh_offpeak)
            modelled_export += Money.from_cents(tariff.export_rate(ts)) * _z(r.aurora_kwh_export)
            if r.aurora_dollar_supply is not None:
                # One modelled day per day Aurora actually billed a supply charge for.
                modelled_supply += Money.from_cents(tariff.supply_charge_per_day(ts))

        actual_peak = Money.from_dollars(_total(rows, "aurora_dollar_peak"))
        actual_offpeak = Money.from_dollars(_total(rows, "aurora_dollar_offpeak"))
        # Aurora export dollars are a credit (billed sign may be negative); compare magnitudes.
        actual_export = Money.from_dollars(abs(_total(rows, "aurora_dollar_export")))
        actual_supply = Money.from_dollars(_total(rows, "aurora_dollar_supply"))

        return [
            LineComparison("peak import", modelled_peak, actual_peak),
            LineComparison("off-peak import", modelled_offpeak, actual_offpeak),
            LineComparison("export credit", modelled_export, actual_export),
            LineComparison("supply charge", modelled_supply, actual_supply),
        ]

    def _classifier_check(self, rows, tariff: Tariff) -> ClassifierResult:
        agreements = 0
        disagreements = 0
        mismatched: list[datetime] = []
        for r in rows:
            aurora_peak = self._aurora_designation(r)
            if aurora_peak is None:
                continue  # no import that hour, or ambiguous — nothing to classify
            if tariff.is_peak(r.ts_utc) == aurora_peak:
                agreements += 1
            else:
                disagreements += 1
                mismatched.append(r.ts_utc)
        return ClassifierResult(agreements, disagreements, mismatched)

    @staticmethod
    def _aurora_designation(row) -> bool | None:
        """True if Aurora billed the hour as peak, False as off-peak, None if undetermined."""
        peak = row.aurora_kwh_peak or 0.0
        offpeak = row.aurora_kwh_offpeak or 0.0
        if peak > 0 and offpeak == 0:
            return True
        if offpeak > 0 and peak == 0:
            return False
        return None

    def _end_to_end(
        self,
        snapshot: Snapshot,
        tariff: Tariff,
        label: str,
        factors: CalibrationFactors | None = None,
    ) -> LineComparison:
        """Modelled net dollars for the period vs the total Aurora actually billed."""
        site = snapshot.to_site()
        if factors is not None:
            site = calibrate(site, factors.import_factor, factors.export_factor)
        modelled = CostCalculatorService().calculate(site, tariff).net_cost
        return LineComparison(label, modelled, Money.from_dollars(snapshot.aurora_billed_total()))


def _total(rows, field: str) -> Decimal:
    """Sum a dollar column as Decimal — money is never accumulated as float."""
    return sum((getattr(r, field) or Decimal(0) for r in rows), Decimal(0))


def _z(value: float | None) -> float:
    """Treat a missing Aurora field as zero (an hour may omit its zero-tariff column)."""
    return 0.0 if value is None else value
