"""ValidationService — the point of iteration 1: does the cost model match the Aurora bill?

The target is a **dollar** figure: the modelled net cost of a month against the amount Aurora
actually billed. Everything else here exists to explain the gap when it doesn't match.

Checks, most-isolated first:
  1. Rate/formula in isolation — Aurora's own metered kWh x our tariff rates, per leg (peak
     import, off-peak import, export credit, daily supply), vs Aurora's billed dollars. Tests
     the constants and the formula with no CT error and no classifier error in the way.
  2. Peak-window classifier — our is_peak(ts) against which tariff Aurora billed each hour to
     (a given hour is entirely peak or off-peak in Aurora's data). Tests the peak-window rule
     independent of magnitude.
  3. End-to-end (THE TARGET) — modelled net dollars from the pf:* grid flows against Aurora's
     billed total, reported twice: once raw, and once after CT calibration. The raw residual is
     dominated by the known ~7-16% CT under-read; the calibrated residual is what the rate model
     itself gets wrong. See ``application/calibration.py``.

Aurora's cadences differ and that shapes the arithmetic: kWh are hourly, dollars are DAILY.
Both are summed over the period before comparing, so the comparison is a monthly total, not a
per-interval one.
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
        return abs(self.delta.cents) <= Decimal(str(tolerance_cents))


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
            modelled_peak += Money.from_cents(tariff.peak_rate(ts) * Decimal(str(_z(r.aurora_kwh_peak))))
            modelled_offpeak += Money.from_cents(tariff.offpeak_rate(ts) * Decimal(str(_z(r.aurora_kwh_offpeak))))
            modelled_export += Money.from_cents(tariff.export_rate(ts) * Decimal(str(_z(r.aurora_kwh_export))))
            if r.aurora_dollar_supply is not None:
                # One modelled day per day Aurora actually billed a supply charge for.
                modelled_supply += Money.from_cents(tariff.supply_charge_per_day(ts))

        actual_peak = Money.from_dollars(sum(_z(r.aurora_dollar_peak) for r in rows))
        actual_offpeak = Money.from_dollars(sum(_z(r.aurora_dollar_offpeak) for r in rows))
        # Aurora export dollars are a credit (billed sign may be negative); compare magnitudes.
        actual_export = Money.from_dollars(abs(sum(_z(r.aurora_dollar_export) for r in rows)))
        actual_supply = Money.from_dollars(sum(_z(r.aurora_dollar_supply) for r in rows))

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


def _z(value: float | None) -> float:
    """Treat a missing Aurora field as zero (an hour may omit its zero-tariff column)."""
    return 0.0 if value is None else value
