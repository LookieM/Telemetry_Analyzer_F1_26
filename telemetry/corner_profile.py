"""One lap's corner profile for the live engineer's A/B comparison (pure: frame + corners in, dict out).

Per corner: time through the corner window, time per phase (entry / mid / exit, windows from
``corner_report.corner_phases``), the understeer index per phase and exit traction (from
``corner_balance.lap_balance``, whose exit window runs past the corner end). Values are None where the lap has
no usable samples (e.g. no slip channels).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .corner_balance import PHASES, lap_balance
from .corner_report import corner_phases

MIN_COVERAGE = 0.95  # a lap frame shorter than this share of the lap distance gives no profile


def frame_coverage(frame: pd.DataFrame, track_length: float | None) -> float:
    """Share of the lap distance the frame covers (0 when unknown or empty)."""
    if frame is None or frame.empty or "lap_distance" not in frame.columns or not track_length:
        return 0.0
    d = frame["lap_distance"].to_numpy(dtype=float)
    d = d[np.isfinite(d) & (d >= 0)]
    return float((d.max() - d.min()) / track_length) if d.size else 0.0


def corner_profile(frame: pd.DataFrame, corners: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """`{corner_id: {name, speed_class, time_s, phases: {entry, mid, exit} (s), understeer: {entry, mid, exit}
    (deg, + = understeer), traction (mean |rear slip ratio| on throttle, exit)}}` for the corners the lap covers."""
    f = frame[frame["lap_distance"] >= 0].sort_values("lap_distance").drop_duplicates("lap_distance", keep="last")
    if len(f) < 10 or "lap_time" not in f.columns:
        return {}
    d = f["lap_distance"].to_numpy(dtype=float)
    t = f["lap_time"].to_numpy(dtype=float)
    ok = np.isfinite(d) & np.isfinite(t)
    d, t = d[ok], t[ok]
    if d.size < 10:
        return {}

    def at(m: float) -> float:
        return float(np.interp(m, d, t))

    bal = {r["id"]: r for r in lap_balance(f, corners)["corners"]}
    out: dict[int, dict[str, Any]] = {}
    for c in corners:
        if c["start_m"] < d[0] - 1 or c["end_m"] > d[-1] + 1:
            continue  # the lap does not cover this corner
        ph = corner_phases(c)
        b = bal.get(c["id"], {})
        out[int(c["id"])] = {
            "name": c["name"],
            "speed_class": c["speed_class"],
            "time_s": at(c["end_m"]) - at(c["start_m"]),
            "phases": {p: at(ph[p][1]) - at(ph[p][0]) for p in PHASES},
            "understeer": {p: b.get(p) for p in PHASES},
            "traction": b.get("traction"),
        }
    return out
