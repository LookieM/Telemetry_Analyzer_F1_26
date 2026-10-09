"""
Streamlit wrappers for the uPlot trace chart and the stint timeline (inline CCv2 components).

uPlot (MIT, vendored in assets/uplot, v1.6.32) is prepended to the chart module, so the app
needs no network, npm or build step.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from ..resample import distance_grid, resample_by_distance  # noqa: F401  (re-exported)

_ASSETS = Path(__file__).resolve().parent / "assets"


def _asset(name: str) -> str:
    return (_ASSETS / name).read_text(encoding="utf-8")


# Registered once at import time (re-registering a name inside a render function misbehaves).
_TRACE_CHART = st.components.v2.component(
    "telemetria_trace_chart",
    html='<div class="tc-root"></div>\n',
    css=_asset("uplot/uPlot.min.css") + "\n" + _asset("trace_chart.css"),
    js=_asset("uplot/uPlot.iife.min.js") + "\n" + _asset("trace_chart.js"),
)
_STINT_TIMELINE = st.components.v2.component(
    "telemetria_stint_timeline",
    html='<div class="st-root"></div>\n',
    css=_asset("stint_timeline.css"),
    js=_asset("stint_timeline.js"),
)


def _values(arr: Any, decimals: int = 4) -> list[float | None]:
    """JSON-safe list: NaN/inf -> null, rounded to keep the payload small."""
    a = np.asarray(arr, dtype=float)
    a = np.round(a, decimals)
    return [float(v) if np.isfinite(v) else None for v in a]


def series(label: str, values: Any, *, color: str | None = None, dash: bool = False, **extra: Any) -> dict[str, Any]:
    """One line in a pane. extra: width, decimals, mode ("points" | "step"), size."""
    out = {"label": label, "values": values, "color": color, "dash": dash}
    out.update(extra)
    return out


def pane(title: str, series_list: Sequence[dict[str, Any]], *, unit: str = "", **extra: Any) -> dict[str, Any]:
    """A stacked chart panel. extra: height, range [lo, hi], decimals, axis_decimals."""
    out = {"title": title, "unit": unit, "series": list(series_list)}
    out.update(extra)
    return out


def trace_chart(
    x: Any,
    panes: Sequence[dict[str, Any]],
    *,
    key: str,
    x_label: str = "Distance (m)",
    x_decimals: int = 0,
    bands: Sequence[dict[str, Any]] | None = None,
    markers: Sequence[dict[str, Any]] | None = None,
    cursor_x: float | None = None,
    sync: str = "lap",
    empty_text: str | None = None,
) -> float | None:
    """
    Stacked panes sharing the x axis: one cursor, drag-to-zoom on every pane, double-click to reset.

    bands: [{from, to, label?, color?}] shaded spans (corners, stints).
    markers: [{x, label?, color?}] dashed vertical lines (pit stops).
    Charts with the same `sync` key move their cursors together (across tabs too).
    Returns the x value the user clicked on this run, else None.
    """
    payload: dict[str, Any] = {
        "x": _values(x),
        "x_label": x_label,
        "x_decimals": x_decimals,
        "sync": sync,
        "panes": [
            {**p, "series": [{**s, "values": _values(s["values"])} for s in p["series"]]} for p in panes
        ],
        "bands": list(bands or []),
        "markers": list(markers or []),
        "empty_text": empty_text,
    }
    payload["sig"] = hashlib.md5(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    payload["cursor_x"] = None if cursor_x is None else float(cursor_x)
    result = _TRACE_CHART(key=key, data=payload, on_clicked_x_change=lambda: None)
    value = getattr(result, "clicked_x", None)
    return float(value) if value is not None else None


def stint_timeline(
    rows: Sequence[dict[str, Any]],
    *,
    laps_total: int,
    key: str,
    show_axis: bool = True,
) -> None:
    """
    Stint bars. rows: [{label, note?, stints: [{from, to, color, text?, title?, light?}]}].
    `light` marks pale compounds (hard) so the label is drawn dark.
    """
    _STINT_TIMELINE(key=key, data={"rows": list(rows), "laps_total": int(laps_total), "show_axis": show_axis})
