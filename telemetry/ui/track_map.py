"""Track map component: live channel readout on hover, click-to-pin, cursor shared with trace charts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

import pandas as pd
import streamlit as st

from ..map_data import (  # noqa: F401  (re-exported)
    BRAKE_SCALE,
    COLOR_CHANNELS,
    DELTA_SCALE,
    MAP_CHANNELS,
    SEQ_SCALE,
    lap_map_payload,
)
from .uplot import _asset

_TRACK_MAP = st.components.v2.component(
    "telemetria_track_map",
    html='<div class="tm-root"></div>\n',
    css=_asset("track_map.css"),
    js=_asset("track_map.js"),
)


def lap_map(
    focus_df: pd.DataFrame,
    *,
    key: str,
    ref_df: pd.DataFrame | None = None,
    color: str = "speed",
    outline: dict | None = None,
    corners: Sequence[Any] | None = None,
    pinned_d: float | None = None,
    cmp_label: str = "Lap",
    ref_label: str = "Ref",
    title: str | None = None,
    height: int = 520,
    step_m: float = 2.0,
    sync: str = "lap",
) -> float | None:
    """
    Racing line of `focus_df` coloured by a channel (or by time delta vs `ref_df`).

    Hovering shows every channel at that point (focus, reference and difference) and moves the
    cursor on trace charts with the same `sync` key; clicking pins the cursor. Returns the
    clicked lap distance on this run, else None.
    """
    payload: dict[str, Any] = {"height": height, "sync": sync, "title": title}
    payload.update(
        lap_map_payload(
            focus_df,
            ref_df=ref_df,
            color=color,
            outline=outline,
            corners=corners,
            step_m=step_m,
            cmp_label=cmp_label,
            ref_label=ref_label,
        )
    )
    payload["sig"] = hashlib.md5(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    payload["pinned_d"] = None if pinned_d is None else float(pinned_d)
    result = _TRACK_MAP(key=key, data=payload, on_clicked_d_change=lambda: None)
    value = getattr(result, "clicked_d", None)
    return float(value) if value is not None else None

