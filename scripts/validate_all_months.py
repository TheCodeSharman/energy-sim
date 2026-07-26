#!/usr/bin/env python3
"""Run the export + validate cycle over every month of the record and tabulate the error.

The single-month figure answers "does the model reproduce this bill?". Running the whole series
answers a different and more useful question: how big is the error in general, is it stable, and
where does it break down. A model that lands on one month by luck shows up here immediately.

Usage (inside the nix devshell):
    nix develop --command python scripts/validate_all_months.py 2023-11 2026-06
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from energy_sim.application.calibration import calibration_factors
from energy_sim.application.validation import ValidationService
from energy_sim.infrastructure.csv_store import read_snapshot, write_snapshot
from energy_sim.infrastructure.exporter import fetch_rows
from energy_sim.infrastructure.tariff_loader import load_tariff
from energy_sim.infrastructure.victoriametrics import DEFAULT_VM_URL, VictoriaMetricsClient
from energy_sim.interface.cli import DEFAULT_TARIFF, month_bounds


def months(first: str, last: str) -> list[str]:
    y, m = (int(x) for x in first.split("-"))
    ly, lm = (int(x) for x in last.split("-"))
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def main() -> int:
    first, last = sys.argv[1], sys.argv[2]
    outdir = Path(__file__).resolve().parents[1] / "data" / "months"
    outdir.mkdir(parents=True, exist_ok=True)
    client = VictoriaMetricsClient(DEFAULT_VM_URL)
    tariff = load_tariff(DEFAULT_TARIFF)
    service = ValidationService()

    print(f"{'month':9} {'billed':>9} {'measured':>9} {'Δ':>8} {'%':>7} "
          f"{'calibrated':>11} {'Δ':>8} {'%':>7} {'imp×':>6} {'exp×':>6} {'clsfy':>9}")
    rows_out = []
    failed: list[str] = []
    for month in months(first, last):
        path = outdir / f"{month}.csv"
        try:
            if not path.exists():
                start, end = month_bounds(month)
                write_snapshot(path, fetch_rows(client, start, end, 3600))
            snap = read_snapshot(path)
            if not snap.has_aurora or snap.aurora_billed_total() == 0:
                print(f"{month:9} {'— no Aurora billed dollars —':>60}")
                continue
            r = service.validate(snap, tariff)
            f = calibration_factors(snap)
            cl = r.classifier
            agree = f"{cl.agreements}/{cl.agreements + cl.disagreements}"
            print(f"{month:9} {float(r.end_to_end.actual.dollars):9.2f} "
                  f"{float(r.end_to_end.modelled.dollars):9.2f} "
                  f"{float(r.end_to_end.delta.dollars):8.2f} {r.end_to_end.delta_pct or 0:6.1f}% "
                  f"{float(r.end_to_end_calibrated.modelled.dollars):11.2f} "
                  f"{float(r.end_to_end_calibrated.delta.dollars):8.2f} "
                  f"{r.end_to_end_calibrated.delta_pct or 0:6.1f}% "
                  f"{f.import_factor:6.3f} {f.export_factor:6.3f} {agree:>9}")
            rows_out.append((month, float(r.end_to_end.actual.dollars),
                             float(r.end_to_end.delta.dollars),
                             float(r.end_to_end_calibrated.delta.dollars),
                             r.end_to_end_calibrated.delta_pct or 0.0))
        except Exception as exc:  # keep going; a bad month should not stop the sweep
            failed.append(month)
            print(f"{month:9} error: {type(exc).__name__}: {exc}")

    if not rows_out:
        print("\n  *** No month produced a result. This is a failure, not an empty record. ***")
        return 1
    billed = sum(r[1] for r in rows_out)
    raw = sum(r[2] for r in rows_out)
    cal = sum(r[3] for r in rows_out)
    worst = max(rows_out, key=lambda r: abs(r[4]))
    print(f"\n{len(rows_out)} months with billed dollars")
    print(f"  total billed              ${billed:,.2f}")
    print(f"  as measured, summed error ${raw:+,.2f}  ({raw / billed * 100:+.2f}%)")
    print(f"  CT-calibrated, summed     ${cal:+,.2f}  ({cal / billed * 100:+.2f}%)")
    print(f"  mean |monthly calibrated error| "
          f"{sum(abs(r[4]) for r in rows_out) / len(rows_out):.2f}%")
    print(f"  worst month {worst[0]} at {worst[4]:+.1f}%")
    if failed:
        # A partial sweep that prints a confident total is worse than one that fails loudly:
        # a transient export error once silently turned 32 months into 29 and $2,302 into $1,817.
        # Reads are retried inside the VM client now, so anything still here is not transient —
        # and it exits non-zero, because printing the warning was not enough on its own.
        print(f"\n  *** INCOMPLETE: {len(failed)} month(s) failed and are NOT in the totals above "
              f"({', '.join(failed)}). Re-run before trusting these numbers. ***")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
