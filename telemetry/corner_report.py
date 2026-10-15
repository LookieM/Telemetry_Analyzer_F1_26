"""Per-corner comparison of a focus lap against a reference lap (pure: no I/O, no UI).

Time in a corner comes from the aligned time delta at the corner boundaries, so the corner deltas plus the
deltas of the stretches between corners add up to the lap delta. Speeds, brake point, trail braking and the
full-throttle point are measured on each lap's own samples inside / next to the corner window.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .corner_detect import BRAKE_ON, BRAKE_REAL, full_throttle_mask, lap_grid
from .metrics import align_laps, compute_time_delta

BRAKE_LOOKBACK_M = 60.0  # braking this far before the corner window still belongs to it
THROTTLE_LOOKAHEAD_M = 100.0  # full throttle this far after the window still belongs to it
MID_HALF_M = 15.0  # the mid phase is the apex +- this
CALLOUT_BRAKE_M = 5.0
CALLOUT_SPEED_KMH = 3.0
CALLOUT_THROTTLE_M = 5.0
CALLOUT_TIME_S = 0.03
REPORT_COLUMNS = ("lap_distance", "lap_time", "speed", "throttle", "brake")
METRIC_KEYS = ("time_s", "entry_kmh", "vmin_kmh", "exit_kmh", "brake_m", "trail_m", "trail_s", "throttle_m")


def _num(v: float | None) -> float | None:
    return None if v is None or not np.isfinite(v) else float(v)


def _first_run(mask: np.ndarray, lo: int, hi: int) -> tuple[int, int] | None:
    """[start, end) of the first True run inside [lo, hi] (a run already on at lo starts at lo)."""
    idx = np.flatnonzero(mask[lo : hi + 1])
    if not idx.size:
        return None
    start = lo + int(idx[0])
    end = start
    while end < len(mask) and mask[end]:
        end += 1
    return start, end


class _Lap:
    """One lap on a 1 m grid with its cumulative lap time."""

    def __init__(self, frame: pd.DataFrame):
        g = lap_grid(frame)
        self.d = g["d"]
        self.speed, self.throttle, self.brake = g["speed"], g["throttle"], g["brake"]
        f = frame.sort_values("lap_distance").drop_duplicates(subset=["lap_distance"], keep="last")
        self.time = np.interp(self.d, f["lap_distance"].to_numpy(dtype=float), f["lap_time"].to_numpy(dtype=float))
        self.full = full_throttle_mask(self.throttle, self.brake)

    def idx(self, metres: float) -> int:
        return int(np.clip(round(metres - self.d[0]), 0, len(self.d) - 1))

    def metrics(self, corner: dict[str, Any], prev_end: float) -> dict[str, float | None]:
        a, b = self.idx(corner["start_m"]), self.idx(corner["end_m"])
        vmin_i = a + int(np.argmin(self.speed[a : b + 1]))
        out: dict[str, float | None] = {k: None for k in METRIC_KEYS}
        out["time_s"] = _num(self.time[b] - self.time[a])
        out["entry_kmh"], out["exit_kmh"] = _num(self.speed[a]), _num(self.speed[b])
        out["vmin_kmh"] = _num(self.speed[vmin_i])
        lo = self.idx(max(prev_end, corner["start_m"] - BRAKE_LOOKBACK_M))
        run = _first_run(self.brake > BRAKE_REAL, lo, vmin_i)
        if run:
            s, e = run
            out["brake_m"] = float(self.d[s])
            # Trail braking: from where the pedal drops below half its peak until it is released.
            peak = float(self.brake[s:e].max())
            half = np.flatnonzero(self.brake[s:e] >= 0.5 * peak)
            released = np.flatnonzero(self.brake[s:e] > BRAKE_ON)
            if half.size and released.size:
                t0, t1 = s + int(half[-1]), s + int(released[-1])
                out["trail_m"] = float(self.d[t1] - self.d[t0])
                out["trail_s"] = _num(self.time[t1] - self.time[t0])
        hi = self.idx(corner["end_m"] + THROTTLE_LOOKAHEAD_M)
        after = np.flatnonzero(self.full[vmin_i : hi + 1])
        if after.size:
            out["throttle_m"] = float(self.d[vmin_i + int(after[0])])
        return out


def corner_phases(corner: dict[str, Any]) -> dict[str, list[float]]:
    """Entry / mid / exit boundaries (m): mid is the apex +- MID_HALF_M, entry before it, exit after it."""
    start, end, apex = corner["start_m"], corner["end_m"], corner["apex_m"]
    m0 = float(np.clip(apex - MID_HALF_M, start, end))
    m1 = float(np.clip(apex + MID_HALF_M, start, end))
    return {"entry": [start, m0], "mid": [m0, m1], "exit": [m1, end]}


def _diff(focus: dict[str, float | None], ref: dict[str, float | None]) -> dict[str, float | None]:
    return {k: (None if focus[k] is None or ref[k] is None else float(focus[k] - ref[k])) for k in METRIC_KEYS}


def _signed(v: float, decimals: int, unit: str) -> str:
    return f"{'+' if v >= 0 else '−'}{abs(v):.{decimals}f} {unit}"


def callouts(name: str, delta: dict[str, float | None]) -> list[str]:
    """Short sentences from measured differences above the noise; nothing when the corner time is a wash."""
    t = delta["time_s"]
    if t is None or abs(t) < CALLOUT_TIME_S:
        return []
    parts: list[str] = []
    if delta["brake_m"] is not None and abs(delta["brake_m"]) >= CALLOUT_BRAKE_M:
        parts.append(f"brake {abs(delta['brake_m']):.0f} m {'earlier' if delta['brake_m'] < 0 else 'later'}")
    if delta["vmin_kmh"] is not None and abs(delta["vmin_kmh"]) >= CALLOUT_SPEED_KMH:
        parts.append(f"vmin {_signed(delta['vmin_kmh'], 0, 'km/h')}")
    if delta["exit_kmh"] is not None and abs(delta["exit_kmh"]) >= CALLOUT_SPEED_KMH:
        parts.append(f"exit {_signed(delta['exit_kmh'], 0, 'km/h')}")
    if delta["throttle_m"] is not None and abs(delta["throttle_m"]) >= CALLOUT_THROTTLE_M:
        parts.append(f"full throttle {abs(delta['throttle_m']):.0f} m {'later' if delta['throttle_m'] > 0 else 'earlier'}")
    if not parts:
        return [f"{name}: {_signed(t, 2, 's')}, no clear difference in brake point or speeds"]
    return [f"{name}: {', '.join(parts)}, {_signed(t, 2, 's')}"]


def corner_report(focus: pd.DataFrame, ref: pd.DataFrame, corners: list[dict[str, Any]]) -> dict[str, Any]:
    """Corner rows (definition + focus / ref metrics + differences + phases + callouts) and the delta bookkeeping:
    `lap_delta` = `sum_corner_delta` + `straights_delta` (the stretches between corners) - `start_delta`.
    Positive deltas mean the focus lap is slower."""
    missing = [c for c in REPORT_COLUMNS if c not in focus.columns or c not in ref.columns]
    if missing:
        raise ValueError(f"Laps lack {', '.join(missing)}")
    focus, ref = focus[list(REPORT_COLUMNS)], ref[list(REPORT_COLUMNS)]  # no bin_index: align on lap_distance
    aligned = compute_time_delta(align_laps(ref, focus, ["lap_time", "speed"]))
    if aligned.empty or "delta_time" not in aligned.columns:
        raise ValueError("Nothing to compare")
    x = aligned["lap_distance"].to_numpy(dtype=float)
    dt = aligned["delta_time"].to_numpy(dtype=float)
    ok = np.isfinite(dt)
    x, dt = x[ok], dt[ok]
    if not x.size:
        raise ValueError("Nothing to compare")

    def delta_at(m: float) -> float:
        return float(np.interp(m, x, dt))

    lf, lr = _Lap(focus), _Lap(ref)
    rows: list[dict[str, Any]] = []
    prev_end = 0.0
    corner_sum = 0.0
    for c in corners:
        mf, mr = lf.metrics(c, prev_end), lr.metrics(c, prev_end)
        diff = _diff(mf, mr)
        diff["time_s"] = delta_at(c["end_m"]) - delta_at(c["start_m"])
        corner_sum += diff["time_s"]
        rows.append({**c, "focus": mf, "ref": mr, "delta": diff, "phases": corner_phases(c), "callouts": callouts(c["name"], diff)})
        prev_end = c["end_m"]
    edges = [float(x[0])]
    for c in corners:
        edges += [c["start_m"], c["end_m"]]
    edges.append(float(x[-1]))
    straights = sum(delta_at(edges[i + 1]) - delta_at(edges[i]) for i in range(0, len(edges), 2))
    return {
        "corners": rows,
        "lap_delta": float(dt[-1]),
        "sum_corner_delta": float(corner_sum),
        "straights_delta": float(straights),
        "start_delta": float(dt[0]),
    }
