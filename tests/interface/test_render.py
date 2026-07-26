"""CLI report rendering (pure string builders)."""
from datetime import datetime, timezone

from energy_sim.application.calibration import CalibrationFactors
from energy_sim.application.validation import (
    ClassifierResult,
    LineComparison,
    ValidationReport,
)
from energy_sim.domain.cost import CostBreakdown
from energy_sim.domain.money import Money
from energy_sim.interface.cli import render_cost_report, render_validation

UTC = timezone.utc

REPORT = ValidationReport(
    has_aurora=True,
    rate_checks=[LineComparison("peak import", Money.from_dollars(10), Money.from_dollars(10))],
    classifier=ClassifierResult(agreements=100, disagreements=0, mismatched_hours=[]),
    end_to_end=LineComparison("net vs bill (pf:* as measured)",
                              Money.from_dollars(90), Money.from_dollars(100)),
    calibration=CalibrationFactors(import_factor=1.112, export_factor=1.043),
    end_to_end_calibrated=LineComparison("net vs bill (CT-calibrated)",
                                         Money.from_dollars(99), Money.from_dollars(100)),
)


def test_cost_report_shows_components_and_net():
    breakdown = CostBreakdown(
        import_cost=Money.from_dollars(100), export_credit=Money.from_dollars(20),
        supply_charge=Money.from_dollars(5), peak_import_kwh=120.0, offpeak_import_kwh=80.0,
    )
    text = render_cost_report(breakdown, title="June 2026")
    assert "June 2026" in text
    assert "$100.00" in text   # import cost
    assert "$20.00" in text    # export credit
    assert "$85.00" in text    # net = 100 - 20 + 5
    assert "120" in text and "80" in text  # peak/off-peak kWh split


def test_validation_leads_with_the_billed_dollar_comparison():
    text = render_validation(REPORT, tolerance_cents=1.0)
    headline = text.split("Check 1")[0]
    assert "$100.00" in headline          # what Aurora billed
    assert "-10.0%" in headline           # as-measured residual (the CT gap)
    assert "-1.0%" in headline            # calibrated residual (the rate model's own error)


def test_validation_shows_the_calibration_factors():
    text = render_validation(REPORT, tolerance_cents=1.0)
    assert "1.112" in text and "1.043" in text


def test_validation_marks_rate_legs_within_tolerance_as_pass():
    text = render_validation(REPORT, tolerance_cents=1.0)
    assert "PASS" in text
    assert "100" in text  # classifier agreements


def test_validation_flags_missing_aurora():
    report = ValidationReport(has_aurora=False, rate_checks=[],
                              classifier=ClassifierResult(0, 0, []), end_to_end=None)
    text = render_validation(report, tolerance_cents=1.0)
    assert "no Aurora" in text.lower() or "cannot validate" in text.lower()
