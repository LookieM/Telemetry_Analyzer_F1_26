"""Lap trace views on the uPlot component: driver channels for one lap or a lap vs a reference."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from .ui import palette
from .ui.uplot import distance_grid, pane, resample_by_distance, series, trace_chart

TRACE_CHANNELS = ("speed", "throttle", "brake", "gear", "rpm", "steering", "lap_time")


def corner_bands(corners: Sequence[Any] | None) -> list[dict[str, Any]]:
    """Shaded spans for every non-straight corner, labelled with its id (T1, T2-3, ...)."""
    return [
        {"from": float(c.start), "to": float(c.end), "label": c.id}
        for c in (corners or [])
        if getattr(c, "kind", "") != "straight"
    ]


def lap_length(*frames: pd.DataFrame | None) -> float | None:
    vals = [
        float(np.nanmax(f["lap_distance"].to_numpy(dtype=float)))
        for f in frames
        if f is not None and not f.empty and "lap_distance" in f.columns
    ]
    return max(vals) if vals else None


def driver_trace(
    focus_df: pd.DataFrame,
    *,
    key: str,
    ref_df: pd.DataFrame | None = None,
    corners: Sequence[Any] | None = None,
    cursor: float | None = None,
    cmp_label: str = "Lap",
    ref_label: str = "Ref",
    step_m: float = 2.0,
    pane_height: int = 130,
) -> float | None:
    """
    Speed, Δt (with a reference), throttle/brake, gear and steering on one shared distance axis.

    The cursor follows the track map and every other chart with sync="lap".
    Returns the clicked distance on this run, else None.
    """
    length = lap_length(focus_df, ref_df)
    if length is None:
        return trace_chart([], [], key=key, empty_text="No distance channel for this lap.")
    grid = distance_grid(length, step_m)
    f = resample_by_distance(focus_df, TRACE_CHANNELS, grid)
    has_ref = ref_df is not None and not ref_df.empty
    r = resample_by_distance(ref_df, TRACE_CHANNELS, grid) if has_ref else None

    def pair(col: str, title: str, mult: float = 1.0, **kw: Any) -> list[dict[str, Any]]:
        out = [series(f"{title} {cmp_label}", f[col] * mult, color=kw.get("color", palette.FOCUS), **kw.get("extra", {}))]
        if r is not None:
            out.append(
                series(f"{title} {ref_label}", r[col] * mult, color=kw.get("ref_color", palette.REF), dash=True, **kw.get("extra", {}))
            )
        return out

    panes = [pane("Speed", pair("speed", "Speed"), unit="km/h", height=pane_height + 40, decimals=0)]
    if r is not None:
        delta = f["lap_time"] - r["lap_time"]
        panes.append(
            pane(
                f"Δt {cmp_label} − {ref_label}",
                [series("Δt", delta, color=palette.DELTA, width=2)],
                unit="s",
                height=pane_height - 20,
                decimals=3,
                axis_decimals=2,
            )
        )
    panes.append(
        pane(
            "Throttle / Brake",
            pair("throttle", "Thr", 100.0, color=palette.THROTTLE, ref_color=palette.THROTTLE)
            + pair("brake", "Brk", 100.0, color=palette.BRAKE, ref_color=palette.BRAKE),
            unit="%",
            height=pane_height,
            decimals=0,
            range=[-2, 102],
        )
    )
    panes.append(
        pane(
            "Gear",
            pair("gear", "Gear", color=palette.GEAR, ref_color=palette.NEUTRAL, extra={"mode": "step"}),
            height=pane_height - 30,
            decimals=0,
        )
    )
    panes.append(pane("Steering", pair("steering", "Steer"), height=pane_height - 20, decimals=2, axis_decimals=1))
    return trace_chart(grid, panes, key=key, bands=corner_bands(corners), cursor_x=cursor, sync="lap")
