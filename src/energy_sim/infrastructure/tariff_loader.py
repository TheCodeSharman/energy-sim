"""Load a Tariff from a TOML config file (stdlib tomllib).

Keeps the tariff *constants* out of code: config/tariffs.toml is the source of truth.
TOML numbers arrive as floats; we route them through ``Decimal(str(...))`` so the exact
decimal the human wrote (e.g. 31.948) is preserved rather than a binary-float approximation.
"""
from __future__ import annotations

import tomllib
from datetime import date
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from energy_sim.domain.tariff import PeakWindow, Tariff, TariffPeriod


def _dec(value: object) -> Decimal:
    return Decimal(str(value))


def load_tariff(path: str | Path) -> Tariff:
    with open(path, "rb") as f:
        data = tomllib.load(f)

    periods = [
        TariffPeriod(
            valid_from=date.fromisoformat(p["valid_from"]),
            peak_c_kwh=_dec(p["peak_c_kwh"]),
            offpeak_c_kwh=_dec(p["offpeak_c_kwh"]),
            export_c_kwh=_dec(p["export_c_kwh"]),
            supply_c_day=_dec(p["supply_c_day"]),
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
