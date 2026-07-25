"""ValidationService: the iteration-1 checks against Aurora ground truth.

The fixture is one billed day at hourly resolution, rigged so every number is checkable by
hand: Aurora's kWh are exactly 1.25x the pf:* CT readings (a 20% CT under-read), and Aurora's
daily dollars are exactly tariff x Aurora kWh plus a $1.00/day supply charge. So the
uncalibrated end-to-end must come in under the bill, and the calibrated one must land on it.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from energy_sim.application.validation import LineComparison, ValidationService
from energy_sim.domain.money import Money
from energy_sim.domain.tariff import PeakWindow, Tariff, TariffPeriod
from energy_sim.infrastructure.csv_store import Snapshot, SnapshotRow

UTC = timezone.utc
OFFPEAK = datetime(2026, 6, 1, 5, 0, tzinfo=UTC)
PEAK = datetime(2026, 6, 1, 6, 0, tzinfo=UTC)

TARIFF = Tariff(
    periods=[TariffPeriod(valid_from=date(2025, 7, 1), peak_c_kwh=Decimal("31.948"),
                          offpeak_c_kwh=Decimal("14.876"), export_c_kwh=Decimal("8.782"),
                          supply_c_day=Decimal("100.0"))],
    peak_window=PeakWindow(timezone=ZoneInfo("Australia/Hobart"),
                           local_weekdays=frozenset({1, 2, 3, 4, 5}),
                           local_hours=frozenset({7, 8, 9, 16, 17, 18, 19, 20})),
)

# Aurora's daily dollars, all placed on the day's single dollar row (as the exporter does).
DAILY_PEAK = 0.63896        # 2.0 kWh x 31.948c
DAILY_OFFPEAK = 0.14876     # 1.0 kWh x 14.876c
DAILY_EXPORT = -0.04391     # 0.5 kWh x 8.782c, billed as a credit
DAILY_SUPPLY = 1.00
DAILY_TOTAL = 1.74381       # peak + offpeak + export + supply

SNAPSHOT = Snapshot([
    SnapshotRow(ts_utc=OFFPEAK, interval_s=3600, grid_import_kwh=0.8, grid_export_kwh=0.0,
                solar_kwh=0.0, consumption_kwh=0.8,
                aurora_kwh_peak=0.0, aurora_kwh_offpeak=1.0, aurora_kwh_export=0.0,
                aurora_dollar_peak=None, aurora_dollar_offpeak=None, aurora_dollar_export=None),
    SnapshotRow(ts_utc=PEAK, interval_s=3600, grid_import_kwh=1.6, grid_export_kwh=0.4,
                solar_kwh=1.5, consumption_kwh=2.7,
                aurora_kwh_peak=2.0, aurora_kwh_offpeak=0.0, aurora_kwh_export=0.5,
                aurora_dollar_peak=DAILY_PEAK, aurora_dollar_offpeak=DAILY_OFFPEAK,
                aurora_dollar_export=DAILY_EXPORT,
                aurora_dollar_supply=DAILY_SUPPLY, aurora_dollar_total=DAILY_TOTAL),
])


def _leg(report, label: str) -> LineComparison:
    return {c.label: c for c in report.rate_checks}[label]


# --- check 1: the rate model in isolation (Aurora's own kWh x our rates) -------

def test_rate_model_matches_aurora_dollars_per_leg():
    report = ValidationService().validate(SNAPSHOT, TARIFF)
    for label, expected in [("peak import", "0.63896"),
                            ("off-peak import", "0.14876"),
                            ("export credit", "0.04391"),
                            ("supply charge", "1.00")]:
        leg = _leg(report, label)
        assert leg.modelled == leg.actual == Money.from_dollars(expected), label


# --- check 2: the peak-window classifier --------------------------------------

def test_classifier_agrees_with_aurora_split():
    report = ValidationService().validate(SNAPSHOT, TARIFF)
    assert report.classifier.agreements == 2
    assert report.classifier.disagreements == 0
    assert report.classifier.mismatched_hours == []


# --- check 3: the target — modelled net dollars vs the actual bill -------------

def test_end_to_end_compares_modelled_net_cost_to_the_billed_total():
    report = ValidationService().validate(SNAPSHOT, TARIFF)
    # pf:* usage 0.8x14.876 + 1.6x31.948 - 0.4x8.782 = 59.5048c, plus 100c supply
    assert report.end_to_end.modelled == Money.from_dollars("1.595048")
    assert report.end_to_end.actual == Money.from_dollars(str(DAILY_TOTAL))


def test_uncalibrated_end_to_end_falls_short_because_the_cts_read_low():
    report = ValidationService().validate(SNAPSHOT, TARIFF)
    assert report.end_to_end.delta.cents < 0


def test_calibration_factors_come_from_auroras_metered_kwh():
    report = ValidationService().validate(SNAPSHOT, TARIFF)
    assert report.calibration.import_factor == pytest.approx(1.25)   # 3.0 billed / 2.4 measured
    assert report.calibration.export_factor == pytest.approx(1.25)   # 0.5 billed / 0.4 measured


def test_calibrated_end_to_end_lands_on_the_bill():
    report = ValidationService().validate(SNAPSHOT, TARIFF)
    assert report.end_to_end_calibrated.actual == Money.from_dollars(str(DAILY_TOTAL))
    assert report.end_to_end_calibrated.within(0.001), report.end_to_end_calibrated.delta


# --- degenerate input ---------------------------------------------------------

def test_no_aurora_data_reports_unvalidatable():
    empty = Snapshot([
        SnapshotRow(ts_utc=OFFPEAK, interval_s=3600, grid_import_kwh=1.0, grid_export_kwh=0.0,
                    solar_kwh=None, consumption_kwh=None,
                    aurora_kwh_peak=None, aurora_kwh_offpeak=None, aurora_kwh_export=None,
                    aurora_dollar_peak=None, aurora_dollar_offpeak=None, aurora_dollar_export=None),
    ])
    report = ValidationService().validate(empty, TARIFF)
    assert report.has_aurora is False
    assert report.end_to_end is None
    assert report.calibration is None


def test_line_comparison_delta_and_pct():
    c = LineComparison(label="x", modelled=Money.from_dollars(9), actual=Money.from_dollars(10))
    assert c.delta == Money.from_dollars(-1)
    assert c.delta_pct == -10.0
