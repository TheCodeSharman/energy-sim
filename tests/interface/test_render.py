"""CLI report rendering (pure string builders)."""
from datetime import datetime, timezone

from energy_sim.application.calibration import CalibrationFactors
from energy_sim.application.validation import (
    ClassifierResult,
    LineComparison,
    ValidationReport,
)
from energy_sim.domain.cost import CostBreakdown
from energy_sim.domain.site import BalanceError
from energy_sim.domain.money import Money
from energy_sim.infrastructure.csv_store import SnapshotRow
from energy_sim.interface.cli import (
    render_cost_report,
    render_export_summary,
    render_interval_consistency,
    render_validation,
)

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


# --- export summary: say what the snapshot does NOT contain --------------------

def _flow_row(ts, grid_import, solar):
    return SnapshotRow(ts_utc=ts, interval_s=3600,
                       grid_import_kwh=grid_import, grid_export_kwh=0.0,
                       solar_kwh=solar, consumption_kwh=solar,
                       aurora_kwh_peak=None, aurora_kwh_offpeak=None, aurora_kwh_export=None,
                       aurora_dollar_peak=None, aurora_dollar_offpeak=None,
                       aurora_dollar_export=None)


T0 = datetime(2026, 6, 1, 5, 0, tzinfo=UTC)
T1 = datetime(2026, 6, 1, 6, 0, tzinfo=UTC)


def test_export_summary_reports_totals():
    summary = render_export_summary([_flow_row(T0, 1.0, 0.5)], "june.csv", 3600)
    assert "1 rows" in summary and "import 1.0 kWh" in summary


def test_export_summary_names_the_intervals_built_from_partial_coverage():
    rows = [_flow_row(T0, 1.0, None), _flow_row(T1, 2.0, 0.5)]
    assert "1 interval(s) with incomplete" in render_export_summary(rows, "june.csv", 3600)


def test_export_summary_stays_quiet_when_coverage_is_complete():
    rows = [_flow_row(T0, 1.0, 0.5), _flow_row(T1, 2.0, 0.5)]
    assert "incomplete" not in render_export_summary(rows, "june.csv", 3600)


# --- what the identity residual actually detects --------------------------------

def _breach(hour, kwh):
    return BalanceError(ts_utc=datetime(2026, 6, 4, hour, tzinfo=UTC), discrepancy_kwh=kwh)


def test_no_breaches_says_so_plainly():
    assert "consistent" in render_interval_consistency([], 0.01).lower()


def test_breaches_are_not_called_an_energy_balance_failure():
    # `pf:consumption_w` IS `solar + grid` by construction, so the identity cannot fail on
    # metering grounds. Calling it "energy balance" invites exactly that misreading.
    out = render_interval_consistency([_breach(18, -1.086)], 0.01)
    assert "energy-balance" not in out.lower()
    assert "energy balance" not in out.lower()


def test_breaches_are_explained_as_differing_sample_density():
    out = render_interval_consistency([_breach(18, -1.086)], 0.01)
    assert "sample" in out.lower()


def test_the_worst_offenders_are_named_so_they_can_be_looked_up():
    out = render_interval_consistency([_breach(18, -1.086), _breach(15, -0.030)], 0.01)
    assert "2026-06-04 18:00" in out
    assert "-1.086" in out


def test_the_count_and_tolerance_are_reported():
    out = render_interval_consistency([_breach(18, -1.086)], 0.01)
    assert "1 interval" in out and "0.01" in out
