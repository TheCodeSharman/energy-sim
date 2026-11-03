"""Backfill myenergi Zappi hourly history from the myenergi cloud.

Fills the Aug-2025 -> May-2026 gap that VM never scraped (device-level scraping only began
2026-05-22, though the Zappi was installed ~Jul/Aug 2025). The myenergi cloud is authoritative
and holds the whole record.

Credentials come from the environment so the API key never lands in a transcript:

    export MYENERGI_SERIAL=22299475          # hub/gateway serial (your Zappi is its own hub)
    export MYENERGI_API_KEY='xxxxxxxx'       # myenergi app -> Settings -> Advanced -> API key
    PYTHONPATH=./src python3 scripts/fetch_myenergi_history.py 2025-08-01 2026-11-03

Writes data/ev_hourly_myenergi.csv  (timestamp_utc, ev_kwh, ev_green_kwh) — same shape as the
scratch _ev_hourly.csv, so scripts/battery_whatif.py can read it directly.

Deliberately fetches the VM-overlap window too (>= 2026-05-22): the monthly totals it prints
there must match what VM already has (~938 kWh total, ~760 green over May-Oct 2026). That
agreement is what validates the field mapping and the Joule->kWh conversion before we trust the
earlier, un-cross-checkable backfill period. Same discipline as the rest of this project.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from urllib.request import (
    HTTPDigestAuthHandler,
    HTTPPasswordMgrWithDefaultRealm,
    build_opener,
)

SERIAL = os.environ.get("MYENERGI_SERIAL")
KEY = os.environ.get("MYENERGI_API_KEY")
if not SERIAL or not KEY:
    sys.exit("Set MYENERGI_SERIAL and MYENERGI_API_KEY in the environment (see module docstring).")

DIRECTOR = "director.myenergi.net"
OUT = Path(__file__).resolve().parents[1] / "data" / "ev_hourly_myenergi.csv"
J_TO_KWH = 1.0 / 3_600_000.0  # myenergi day/hour energies are Joules (watt-seconds)


def _opener(host: str):
    mgr = HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, f"https://{host}", SERIAL, KEY)
    return build_opener(HTTPDigestAuthHandler(mgr))


def discover_asn() -> str:
    """The director replies with an x_myenergi-asn header naming the regional server to use."""
    op = _opener(DIRECTOR)
    req = urllib.request.Request(f"https://{DIRECTOR}/cgi-jstatus-*")
    with op.open(req, timeout=30) as r:
        asn = r.headers.get("x_myenergi-asn")
    if not asn:
        sys.exit("No x_myenergi-asn header from director; check serial/API key.")
    return asn


def _records(payload: dict) -> list[dict]:
    """The day response is {'U<serial>': [ {hour record}, ... ]}; find that list robustly."""
    for v in payload.values():
        if isinstance(v, list):
            return v
    return []


def fetch_day(host: str, day: dt.date) -> list[tuple[dt.datetime, float, float]]:
    url = f"https://{host}/cgi-jdayhour-Z{SERIAL}-{day:%Y-%m-%d}"
    op = _opener(host)
    try:
        with op.open(url, timeout=30) as r:
            payload = json.load(r)
    except Exception as e:  # offline day / transient — skip, don't fabricate
        print(f"  {day}: skipped ({e})", file=sys.stderr)
        return []
    out = []
    for rec in _records(payload):
        hr = int(rec.get("hr", 0))
        ts = dt.datetime(int(rec["yr"]), int(rec["mon"]), int(rec["dom"]), hr,
                         tzinfo=dt.timezone.utc)
        # single phase: h1d = diverted (solar/green), h1b = imported/boosted (grid charge)
        green = float(rec.get("h1d", 0)) * J_TO_KWH
        grid = float(rec.get("h1b", 0)) * J_TO_KWH
        total = green + grid
        if total > 0:
            out.append((ts, round(total, 4), round(green, 4)))
    return out


def main():
    start = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date(2025, 8, 1)
    end = dt.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else dt.date.today()
    host = discover_asn()
    print(f"myenergi server: {host}; fetching Z{SERIAL} {start}..{end}")

    rows = []
    d = start
    while d <= end:
        rows.extend(fetch_day(host, d))
        time.sleep(0.4)  # be gentle on the cloud API
        d += dt.timedelta(days=1)
    rows.sort()

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp_utc", "ev_kwh", "ev_green_kwh"])
        for ts, t, g in rows:
            w.writerow([ts.strftime("%Y-%m-%dT%H:%M:%SZ"), t, g])

    monthly = defaultdict(lambda: [0.0, 0.0])
    for ts, t, g in rows:
        m = monthly[ts.strftime("%Y-%m")]
        m[0] += t; m[1] += g
    print(f"\nwrote {len(rows)} hours to {OUT}")
    print("month      total kWh   green kWh   (cross-check >=2026-05 against VM: ~938 / ~760)")
    for mth in sorted(monthly):
        t, g = monthly[mth]
        print(f"  {mth}    {t:>8.1f}   {g:>8.1f}")


if __name__ == "__main__":
    main()
