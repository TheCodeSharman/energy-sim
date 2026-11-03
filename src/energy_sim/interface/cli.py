"""Command-line interface: export / cost-report / validate.

Rendering is done by pure functions (``render_*``) so it can be unit-tested; ``main`` only
parses args and does IO.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from energy_sim.application.battery_dispatch import SelfConsumptionDispatch
from energy_sim.application.cost_calculator import CostCalculatorService
from energy_sim.application.validation import ValidationReport, ValidationService
from energy_sim.domain.battery import Battery
from energy_sim.domain.cost import CostBreakdown
from energy_sim.domain.site import BalanceError
from energy_sim.infrastructure.csv_store import (
    Snapshot,
    SnapshotRow,
    read_snapshot,
    write_snapshot,
)
from energy_sim.infrastructure.exporter import fetch_rows
from energy_sim.infrastructure.tariff_loader import load_tariff
from energy_sim.infrastructure.victoriametrics import DEFAULT_VM_URL, VictoriaMetricsClient

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TARIFF = REPO_ROOT / "config" / "tariffs.toml"

# Aurora bills on local calendar days (Tasmania), so a "month" is a local month.
BILLING_TZ = ZoneInfo("Australia/Hobart")


# --- rendering (pure) ---------------------------------------------------------

def render_cost_report(breakdown: CostBreakdown, title: str) -> str:
    lines = [
        f"Cost report — {title}",
        "-" * 48,
        f"  Import cost      {str(breakdown.import_cost):>12}",
        f"  Export credit    {str(breakdown.export_credit):>12}",
        f"  Supply charge    {str(breakdown.supply_charge):>12}",
        f"  {'Net cost':<15}  {str(breakdown.net_cost):>12}",
        "",
        f"  Peak import      {breakdown.peak_import_kwh:>10.1f} kWh",
        f"  Off-peak import  {breakdown.offpeak_import_kwh:>10.1f} kWh",
    ]
    return "\n".join(lines)


def render_battery_report(baseline: CostBreakdown, with_battery: CostBreakdown,
                          title: str, battery_label: str) -> str:
    saving = baseline.net_cost - with_battery.net_cost
    return "\n".join([
        f"Battery what-if — {title}",
        "-" * 48,
        f"  Battery: {battery_label}",
        "",
        f"  Net cost (no battery)  {str(baseline.net_cost):>12}",
        f"  Net cost (battery)     {str(with_battery.net_cost):>12}",
        f"  {'Saving':<17}    {str(saving):>12}",
    ])


def render_export_summary(rows: list[SnapshotRow], out: str, step_seconds: int) -> str:
    """What was written — and, when the sources had holes, how much of it is missing."""
    snapshot = Snapshot(rows)
    line = (f"Wrote {len(rows)} rows to {out} (step {step_seconds}s; "
            f"import {snapshot.pf_import_kwh_total():.1f} kWh, "
            f"export {snapshot.pf_export_kwh_total():.1f} kWh)")
    incomplete = snapshot.incomplete_rows()
    if incomplete:
        line += (f"\n  {len(incomplete)} interval(s) with incomplete pf:* coverage "
                 f"(first {incomplete[0].ts_utc:%Y-%m-%d %H:%M}Z): a blank column is an "
                 f"interval nothing measured, so totals over it are short by that much.")
    return line


def render_interval_consistency(errors: list[BalanceError], tolerance_kwh: float) -> str:
    """Report the identity residual as the sampling artefact it is.

    This was labelled "energy balance", which invites the reading that it validates metering.
    It cannot: `pf:consumption_w` is *defined* as `solar + grid`, so the identity holds by
    construction at every instant it is evaluated.

    What it actually catches is an interval whose series were averaged over DIFFERENT numbers of
    samples. `avg_over_time` averages each series over its own samples, and the fallback chains
    are independent — so when solar drops to a sparser tier while grid stays hi-res, the row
    combines (say) a 1-sample solar average with a 60-sample grid average and presents both as
    covering the same hour. Verified over June 2026: all 13 breaches had fewer solar samples
    than grid samples, and the three worst had exactly one.
    """
    if not errors:
        return "Interval consistency — all intervals consistent."
    worst = sorted(errors, key=lambda e: -abs(e.discrepancy_kwh))[:5]
    lines = [
        f"Interval consistency — {len(errors)} interval(s) where consumption differs from "
        f"solar + import - export by more than {tolerance_kwh} kWh.",
        "  Not a metering disagreement: pf:consumption_w is solar + grid by construction. These",
        "  are intervals whose pf:* series were averaged over different sample counts — solar on",
        "  a sparser fallback tier than grid — so the row mixes averages of unequal coverage.",
    ]
    lines += [f"    {e.ts_utc:%Y-%m-%d %H:%M}Z  {e.discrepancy_kwh:+.3f} kWh" for e in worst]
    if len(errors) > len(worst):
        lines.append(f"    (+{len(errors) - len(worst)} more)")
    return "\n".join(lines)


def _residual(comparison) -> str:
    pct = "n/a" if comparison.delta_pct is None else f"{comparison.delta_pct:+.1f}%"
    return (f"modelled {str(comparison.modelled):>11}  actual {str(comparison.actual):>11}"
            f"  Δ {str(comparison.delta):>10}  {pct:>7}")


def render_validation(report: ValidationReport, tolerance_cents: float) -> str:
    if not report.has_aurora:
        return ("Validation — no Aurora billed data in this snapshot; cannot validate against "
                "the bill.\n(Re-export a period where Aurora hourly data exists.)")

    lines = [
        "Validation against Aurora billed data",
        "=" * 60,
        "",
        "THE NUMBER — modelled net cost vs what Aurora actually billed:",
        f"  as measured   {_residual(report.end_to_end)}",
    ]
    if report.end_to_end_calibrated is not None:
        lines.append(f"  CT-calibrated {_residual(report.end_to_end_calibrated)}")
    if report.calibration is not None:
        c = report.calibration
        lines += [
            "",
            "  CT calibration (Aurora metered kWh / pf:* measured kWh):",
            f"    import x{c.import_factor:.3f}    export x{c.export_factor:.3f}",
            "  (>1 means the household CTs read low. Calibrating removes that metering bias, so",
            "   the calibrated residual above is the rate model's own error.)",
        ]

    lines += [
        "",
        f"(pass tolerance: {tolerance_cents:.2f}c per leg)",
        "",
        "Check 1 — rate/formula in isolation (Aurora kWh x our rates vs Aurora $):",
    ]
    for c in report.rate_checks:
        verdict = "PASS" if c.within(tolerance_cents) else "FAIL"
        lines.append(
            f"  {c.label:<16} modelled {str(c.modelled):>11}  actual {str(c.actual):>11}"
            f"  Δ {str(c.delta):>9}  [{verdict}]"
        )

    cl = report.classifier
    total = cl.agreements + cl.disagreements
    lines += [
        "",
        "Check 2 — peak-window classifier vs Aurora's own hourly split:",
        f"  {cl.agreements}/{total} hours agree, {cl.disagreements} disagree",
    ]
    if cl.mismatched_hours:
        shown = ", ".join(ts.strftime("%Y-%m-%d %H:%MZ") for ts in cl.mismatched_hours[:5])
        more = "" if len(cl.mismatched_hours) <= 5 else f" (+{len(cl.mismatched_hours) - 5} more)"
        lines.append(f"  mismatched: {shown}{more}")

    return "\n".join(lines)


# --- IO commands --------------------------------------------------------------

def month_bounds(month: str) -> tuple[datetime, datetime]:
    """UTC [start, end) bounds of a ``YYYY-MM`` month in the BILLING timezone.

    Aurora bills by local calendar day and stamps each day at local midnight, so a naive UTC
    month window is offset by the UTC offset: it drops the month's first billed day and gains
    the following month's first. Resolving the month in ``BILLING_TZ`` (DST included) keeps the
    pf:* flows and the Aurora dollars over exactly the same real days.
    """
    year, mon = (int(x) for x in month.split("-"))
    start = datetime(year, mon, 1, tzinfo=BILLING_TZ)
    end = datetime(year + (mon == 12), (mon % 12) + 1, 1, tzinfo=BILLING_TZ)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _cmd_export(args) -> None:
    start, end = month_bounds(args.month)
    client = VictoriaMetricsClient(args.vm_url)
    rows = fetch_rows(client, start, end, args.step_seconds)
    write_snapshot(args.out, rows)
    print(render_export_summary(rows, args.out, args.step_seconds))


def _cmd_cost_report(args) -> None:
    snapshot = read_snapshot(args.infile)
    tariff = load_tariff(args.tariff)
    breakdown = CostCalculatorService().calculate(snapshot.to_site(), tariff)
    print(render_cost_report(breakdown, title=Path(args.infile).stem))


def _cmd_battery(args) -> None:
    snapshot = read_snapshot(args.infile)
    tariff = load_tariff(args.tariff)
    site = snapshot.to_site()
    baseline = CostCalculatorService().calculate(site, tariff)
    battery = Battery(name="battery", usable_kwh=args.usable_kwh, max_power_kw=args.power_kw,
                      round_trip_efficiency=args.round_trip)
    adjusted = SelfConsumptionDispatch().apply(site, battery)
    with_battery = CostCalculatorService().calculate(adjusted, tariff)
    label = (f"{args.usable_kwh:g} kWh usable, {args.power_kw:g} kW, "
             f"{args.round_trip:g} round-trip")
    print(render_battery_report(baseline, with_battery, Path(args.infile).stem, label))


def _cmd_validate(args) -> None:
    snapshot = read_snapshot(args.infile)
    tariff = load_tariff(args.tariff)
    report = ValidationService().validate(snapshot, tariff)
    print(render_validation(report, tolerance_cents=args.tolerance_cents))

    errors = snapshot.to_site().energy_balance_errors(tolerance_kwh=args.balance_tolerance_kwh)
    print()
    print(render_interval_consistency(errors, args.balance_tolerance_kwh))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="energy_sim", description="Home energy-cost simulator.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="Snapshot a month from VictoriaMetrics to CSV.")
    p_export.add_argument("--month", required=True,
                          help="YYYY-MM — a local billing month, not a UTC one")
    p_export.add_argument("--out", required=True, help="Output CSV path")
    p_export.add_argument("--step-seconds", type=int, default=3600, dest="step_seconds")
    p_export.add_argument("--vm-url", default=DEFAULT_VM_URL, dest="vm_url")
    p_export.set_defaults(func=_cmd_export)

    p_cost = sub.add_parser("cost-report", help="Cost breakdown for a snapshot.")
    p_cost.add_argument("--in", required=True, dest="infile", help="Snapshot CSV path")
    p_cost.add_argument("--tariff", default=str(DEFAULT_TARIFF))
    p_cost.set_defaults(func=_cmd_cost_report)

    p_batt = sub.add_parser("battery", help="Battery what-if: cost saving vs the no-battery baseline.")
    p_batt.add_argument("--in", required=True, dest="infile", help="Snapshot CSV path")
    p_batt.add_argument("--tariff", default=str(DEFAULT_TARIFF))
    p_batt.add_argument("--usable-kwh", type=float, required=True, dest="usable_kwh")
    p_batt.add_argument("--power-kw", type=float, default=5.0, dest="power_kw")
    p_batt.add_argument("--round-trip", type=float, default=0.9, dest="round_trip")
    p_batt.set_defaults(func=_cmd_battery)

    p_val = sub.add_parser("validate", help="Validate a snapshot against Aurora billed data.")
    p_val.add_argument("--in", required=True, dest="infile", help="Snapshot CSV path")
    p_val.add_argument("--tariff", default=str(DEFAULT_TARIFF))
    p_val.add_argument("--tolerance-cents", type=float, default=1.0, dest="tolerance_cents")
    p_val.add_argument("--balance-tolerance-kwh", type=float, default=0.01, dest="balance_tolerance_kwh")
    p_val.set_defaults(func=_cmd_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Exit status is the contract: 0 only if the command did what it was asked to do.

    A read that could not be completed raises out of here rather than being turned into a
    smaller, quieter answer.
    """
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0
