"""Load a Tariff from a TOML config file (stdlib tomllib).

Keeps the tariff *constants* out of code: config/tariffs.toml is the source of truth.
"""
from __future__ import annotations

import tomllib
from datetime import date
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from energy_sim.domain.tariff import PeakWindow, Tariff, TariffPeriod


def load_tariff(path: str | Path) -> Tariff:
    with open(path, "rb") as f:
        data = tomllib.load(f)

    periods = [
        TariffPeriod(
            valid_from=date.fromisoformat(p["valid_from"]),
            peak_c_kwh=Decimal(p["peak_c_kwh"]),
            offpeak_c_kwh=Decimal(p["offpeak_c_kwh"]),
            export_c_kwh=Decimal(p["export_c_kwh"]),
            supply_c_day=Decimal(p["supply_c_day"]),
        )
        for p in data["period"]
    ]

    window = data["peak_window"]
    peak_window = PeakWindow(
        timezone=ZoneInfo(window["timezone"]),
        local_weekdays=frozenset(window["local_weekdays"]),
        local_hours=frozenset(window["local_hours"]),
    )
    billing_tz = data.get("billing", {}).get("timezone")
    return Tariff(
        periods=periods,
        peak_window=peak_window,
        billing_timezone=ZoneInfo(billing_tz) if billing_tz else None,
    )
