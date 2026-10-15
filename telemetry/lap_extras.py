"""Extra lap-trace channels (g-forces, per-wheel slip / temperatures): which columns carry them and whether a session has data."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import channels as ch


@dataclass(frozen=True)
class Extra:
    key: str
    label: str
    unit: str
    sources: tuple[str, ...]  # registry channel keys tried in order
    per_wheel: bool


EXTRAS: tuple[Extra, ...] = (
    Extra("g_lat", "Lateral g", "g", ("g_lat",), False),
    Extra("g_long", "Longitudinal g", "g", ("g_long",), False),
    Extra("slip_angle", "Slip angle", "rad", ("wheel_slip_angle",), True),
    Extra("slip_ratio", "Slip ratio", "", ("wheel_slip_ratio",), True),
    Extra("tyre_surface", "Tyre surface temp", "°C", ("tyre_surface_temp", "tyre_temp"), True),
    Extra("tyre_inner", "Tyre inner temp", "°C", ("tyre_inner_temp",), True),
)
BY_KEY = {e.key: e for e in EXTRAS}


def output_names(extra: Extra) -> list[str]:
    """Names the extra goes by in API payloads: the key, or `<key>_FL` ... `<key>_RR` (front-first)."""
    return [f"{extra.key}_{w}" for w in ch.WHEELS] if extra.per_wheel else [extra.key]


def resolve(extra: Extra, columns) -> dict[str, str]:
    """Output name -> stored column for an extra, {} when the columns are not there."""
    frame = pd.DataFrame(columns=list(columns))
    for src in extra.sources:
        cols = ch.wheel_columns(frame, src) if extra.per_wheel else ([c] if (c := ch.resolve(frame, src)) else None)
        if cols:
            return dict(zip(output_names(extra), cols))
    return {}


def availability(columns, load) -> list[dict]:
    """Per extra: available flag and the reason when not. `load(cols)` returns a frame with those columns."""
    resolved = {e.key: resolve(e, columns) for e in EXTRAS}
    wanted = sorted({c for m in resolved.values() for c in m.values()})
    frame = load(wanted) if wanted else pd.DataFrame()
    out = []
    for e in EXTRAS:
        mapping = resolved[e.key]
        reason = None
        if not mapping:
            reason = "Not recorded in this export"
        elif not all(frame[c].notna().any() for c in mapping.values()):
            reason = "Recorded but empty in this export"
        out.append(
            {
                "key": e.key,
                "label": e.label,
                "unit": e.unit,
                "per_wheel": e.per_wheel,
                "available": reason is None,
                "reason": reason,
                "channels": output_names(e),
            }
        )
    return out
