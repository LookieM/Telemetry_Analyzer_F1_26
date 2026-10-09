"""Pure payload for the track map (positions, hover channels, colouring, corners, outline); no UI imports."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from .resample import distance_grid, resample_by_distance

# Sequential (slow -> fast) and diverging (gain -> loss) scales that read on light and dark themes.
SEQ_SCALE = [[0.0, "#2B4C7E"], [0.35, "#5FA8D3"], [0.7, "#F2C14E"], [1.0, "#D7263D"]]
BRAKE_SCALE = [[0.0, "#9AA0A6"], [1.0, "#D7263D"]]
DELTA_SCALE = [[0.0, "#2E9E44"], [0.5, "#B8BCC2"], [1.0, "#D7263D"]]

# (column, label, unit, multiplier, decimals) shown in the hover readout when present.
MAP_CHANNELS: tuple[tuple[str, str, str, float, int], ...] = (
    ("speed", "Speed", "km/h", 1.0, 0),
    ("throttle", "Throttle", "%", 100.0, 0),
    ("brake", "Brake", "%", 100.0, 0),
    ("gear", "Gear", "", 1.0, 0),
    ("rpm", "RPM", "", 1.0, 0),
    ("steering", "Steer", "", 1.0, 2),
    ("g_lat", "Lat g", "g", 1.0, 2),
    ("g_long", "Long g", "g", 1.0, 2),
    ("ers_store_mj", "ERS", "MJ", 1.0, 2),
    ("lap_time", "Lap time", "s", 1.0, 3),
)
COLOR_CHANNELS = ("speed", "throttle", "brake", "gear", "delta")
MAP_COLUMNS = tuple(c for c, *_ in MAP_CHANNELS)


def _values(arr: Any, decimals: int = 4) -> list[float | None]:
    """JSON-safe list: NaN/inf -> null, rounded to keep the payload small."""
    a = np.round(np.asarray(arr, dtype=float), decimals)
    return [float(v) if np.isfinite(v) else None for v in a]


def map_axes(df: pd.DataFrame) -> tuple[str, str] | None:
    """Horizontal map axes (X/Y on the ground plane, legacy X/Z fallback)."""
    from .plots import _map_xy

    return _map_xy(df)


def lap_map_payload(
    focus_df: pd.DataFrame,
    *,
    ref_df: pd.DataFrame | None = None,
    color: str = "speed",
    outline: dict | None = None,
    corners: Sequence[Any] | None = None,
    step_m: float = 2.0,
    cmp_label: str = "Lap",
    ref_label: str = "Ref",
) -> dict[str, Any]:
    """Racing line of `focus_df` coloured by a channel (or by time delta vs `ref_df`)."""
    payload: dict[str, Any] = {"x": [], "y": [], "d": []}
    axes = map_axes(focus_df) if not focus_df.empty else None
    if axes is None or "lap_distance" not in focus_df.columns:
        return payload
    dist = focus_df["lap_distance"].to_numpy(dtype=float)
    start = max(0.0, float(np.nanmin(dist)))  # positions exist only where the lap has samples
    grid = distance_grid(float(np.nanmax(dist)), step_m)
    grid = grid[grid >= start]
    present = [c for c, *_ in MAP_CHANNELS if c in focus_df.columns]
    f = resample_by_distance(focus_df, [axes[0], axes[1], *present], grid)
    has_ref = ref_df is not None and not ref_df.empty and "lap_distance" in ref_df.columns
    r = resample_by_distance(ref_df, present, grid) if has_ref else None

    channels = []
    for col, label, unit, mult, dec in MAP_CHANNELS:
        if col not in present:
            continue
        ch = {"label": label, "unit": unit, "decimals": dec, "values": _values(f[col] * mult)}
        if r is not None:
            ch["ref"] = _values(r[col] * mult)
        channels.append(ch)
    delta = None
    if r is not None and "lap_time" in present:
        delta = f["lap_time"] - r["lap_time"]
        channels.append({"label": "Δt", "unit": "s", "decimals": 3, "values": _values(delta)})

    payload.update(
        {
            "x": _values(f[axes[0]], 2),
            "y": _values(f[axes[1]], 2),
            "d": _values(grid, 1),
            "channels": channels,
            "cmp_label": cmp_label,
            "ref_label": ref_label,
            "color": _color_payload(color, f, delta),
            "labels": [
                {"text": c.id, "d": float(c.apex)}
                for c in (corners or [])
                if getattr(c, "apex", None) is not None and getattr(c, "kind", "") != "straight"
            ],
            "spans": [
                {"from": float(c.start), "to": float(c.end), "name": c.name}
                for c in (corners or [])
                if getattr(c, "kind", "") != "straight"
            ],
            "outline": (
                {"x": [float(v) for v in outline["x"]], "y": [float(v) for v in outline["y"]]}
                if outline and outline.get("x") and outline.get("y")
                else None
            ),
        }
    )
    return payload


def _color_payload(color: str, f: dict[str, np.ndarray], delta: np.ndarray | None) -> dict[str, Any] | None:
    if color == "delta" and delta is not None:
        finite = np.abs(delta[np.isfinite(delta)])
        span = float(np.percentile(finite, 98)) if finite.size else 0.1
        span = max(span, 0.05)
        return {"values": _values(delta), "min": -span, "max": span, "scale": DELTA_SCALE, "label": "Δt (s)", "decimals": 2}
    col = color if color in f else "speed"
    if col not in f:
        return None
    mult = 100.0 if col in ("throttle", "brake") else 1.0
    vals = f[col] * mult
    finite = vals[np.isfinite(vals)]
    if not finite.size:
        return None
    unit = {"speed": "km/h", "throttle": "%", "brake": "%", "gear": ""}.get(col, "")
    return {
        "values": _values(vals),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "scale": BRAKE_SCALE if col == "brake" else SEQ_SCALE,
        "label": f"{col} ({unit})" if unit else col,
        "decimals": 0,
    }
