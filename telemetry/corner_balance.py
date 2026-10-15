"""Car balance per corner and phase from slip angles, traction on exit and per-wheel lock-ups (pure: no I/O).

Understeer index = mean |slip angle| of the front wheels minus the rear wheels, in degrees, over the samples where
the car is really cornering (|lateral g| above LAT_G_MIN, or steering above STEER_MIN when lateral g is missing).
Positive = understeer, negative = oversteer. Traction = mean |slip ratio| of the rear wheels on the throttle in
the exit phase. A lock-up is a run of a wheel's slip ratio below LOCK_SLIP_RATIO while braking.
Exports are front-first (FL, FR, RL, RR); sessions without slip channels report `available: False`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .channels import FRONT_WHEELS, REAR_WHEELS, WHEELS
from .corner_report import BRAKE_LOOKBACK_M, corner_phases

LAT_G_MIN = 0.5  # |lateral g| above this = cornering
STEER_MIN = 0.15  # |steering| (-1..1) above this = cornering, used where lateral g is missing
MIN_SAMPLES = 4  # fewer cornering samples than this in a phase = no value
TRACTION_THROTTLE = 0.5  # exit traction counts samples with more throttle than this
LOCK_SLIP_RATIO = -0.15  # slip ratio below this while braking = wheel locked
LOCK_BRAKE = 0.2
MIN_LOCK_SAMPLES = 2  # consecutive samples (1 m bins on stored sessions)
# Labels of an understeer index (degrees). The raw index is positive on every car (the front tyres carry the
# steering angle, so front slip > rear slip even when the car feels neutral): the median over the library's clean
# laps is about +2 deg on entry, +3 deg mid corner and +0.2 deg on exit. Labels are given relative to these.
NEUTRAL_DEG = {"entry": 2.0, "mid": 3.0, "exit": 0.2}
US_SLIGHT_DEG = 0.75
US_STRONG_DEG = 2.0
EXIT_EXTRA_M = 40.0  # the exit window runs this far past the corner end (full throttle returns there), up to the next corner
PHASES = ("entry", "mid", "exit")

SLIP_ANGLE = [f"wheel_slip_angle_{i}" for i in range(4)]
SLIP_RATIO = [f"wheel_slip_ratio_{i}" for i in range(4)]
BALANCE_COLUMNS = ("lap", "lap_distance", "throttle", "brake", "steering", "g_lat", *SLIP_ANGLE, *SLIP_RATIO)
NO_SLIP_REASON = "This session has no slip angle / slip ratio channels (compact import); balance needs a full export"


def has_slip_channels(frame: pd.DataFrame) -> bool:
    return all(c in frame.columns for c in (*SLIP_ANGLE, *SLIP_RATIO))


def _col(frame: pd.DataFrame, name: str) -> np.ndarray:
    if name not in frame.columns:
        return np.full(len(frame), np.nan)
    return frame[name].to_numpy(dtype=float)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    if not mask.size:
        return []
    edges = np.flatnonzero(np.diff(np.concatenate(([0], mask.astype(np.int8), [0]))))
    return [(int(a), int(b)) for a, b in zip(edges[0::2], edges[1::2])]


def _mean(a: np.ndarray, mask: np.ndarray, min_n: int) -> float | None:
    v = a[mask & np.isfinite(a)]
    return float(v.mean()) if v.size >= min_n else None


def _corner_of(distance: float, corners: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The corner a lock-up belongs to: its window, or the braking zone up to BRAKE_LOOKBACK_M before it."""
    for c in corners:
        if c["start_m"] - BRAKE_LOOKBACK_M <= distance <= c["end_m"]:
            return {"id": c["id"], "name": c["name"]}
    return None


def balance_phases(corner: dict[str, Any], next_start: float | None) -> dict[str, list[float]]:
    """The corner's entry / mid / exit windows; the exit one is stretched past the corner end (EXIT_EXTRA_M)."""
    phases = corner_phases(corner)
    hi = corner["end_m"] + EXIT_EXTRA_M
    if next_start is not None:
        hi = min(hi, next_start)
    phases["exit"] = [phases["exit"][0], max(hi, phases["exit"][0])]
    return phases


def lap_balance(frame: pd.DataFrame, corners: list[dict[str, Any]]) -> dict[str, Any]:
    """Balance of one lap: per corner {id, entry, mid, exit (understeer index, deg), traction, lockups} + all lock-ups.
    `{available: False, reason}` when the slip channels are missing."""
    if not has_slip_channels(frame):
        return {"available": False, "reason": NO_SLIP_REASON, "corners": [], "lockups": []}
    f = frame[frame["lap_distance"] >= 0].sort_values("lap_distance")
    d = _col(f, "lap_distance")
    angle = np.degrees(np.abs(np.stack([_col(f, c) for c in SLIP_ANGLE])))
    ratio = np.stack([_col(f, c) for c in SLIP_RATIO])
    throttle, brake = _col(f, "throttle"), _col(f, "brake")
    glat, steer = np.abs(_col(f, "g_lat")), np.abs(_col(f, "steering"))
    cornering = np.where(np.isfinite(glat), glat > LAT_G_MIN, steer > STEER_MIN)
    us_sample = angle[list(FRONT_WHEELS)].mean(axis=0) - angle[list(REAR_WHEELS)].mean(axis=0)
    rear_ratio = np.abs(ratio[list(REAR_WHEELS)]).mean(axis=0)

    lockups: list[dict[str, Any]] = []
    for w in range(4):
        for a, b in _runs((ratio[w] < LOCK_SLIP_RATIO) & (brake > LOCK_BRAKE)):
            if b - a >= MIN_LOCK_SAMPLES:
                lockups.append(
                    {"wheel": WHEELS[w], "distance_m": float(d[a]), "length_m": float(d[b - 1] - d[a]), "min_slip_ratio": float(ratio[w, a:b].min())}
                )
    lockups.sort(key=lambda lock: lock["distance_m"])
    for lock in lockups:
        lock["corner"] = _corner_of(lock["distance_m"], corners)

    rows = []
    for i, c in enumerate(corners):
        phases = balance_phases(c, corners[i + 1]["start_m"] if i + 1 < len(corners) else None)
        row: dict[str, Any] = {"id": c["id"]}
        for name in PHASES:
            lo, hi = phases[name]
            row[name] = _mean(us_sample, (d >= lo) & (d <= hi) & cornering, MIN_SAMPLES)
        lo, hi = phases["exit"]
        row["traction"] = _mean(rear_ratio, (d >= lo) & (d <= hi) & (throttle > TRACTION_THROTTLE), MIN_SAMPLES)
        row["lockups"] = {}
        for lock in lockups:
            if lock["corner"] is not None and lock["corner"]["id"] == c["id"]:
                row["lockups"][lock["wheel"]] = row["lockups"].get(lock["wheel"], 0) + 1
        rows.append(row)
    return {"available": True, "reason": None, "corners": rows, "lockups": lockups}


def _median(values: list[float | None]) -> float | None:
    v = [x for x in values if x is not None]
    return float(np.median(v)) if v else None


def session_balance(laps: list[dict[str, Any]], corners: list[dict[str, Any]]) -> dict[str, Any]:
    """Median over several laps' `lap_balance` results (each lap dict also carries `lap`); all lock-ups are kept."""
    ok = [lp for lp in laps if lp["available"]]
    if not ok:
        reason = laps[0]["reason"] if laps else "No clean laps to measure balance on"
        return {"available": False, "reason": reason, "corners": [], "lockups": [], "laps": 0}
    rows = []
    for i, c in enumerate(corners):
        picks = [lp["corners"][i] for lp in ok]
        row: dict[str, Any] = {"id": c["id"]}
        for key in (*PHASES, "traction"):
            row[key] = _median([p[key] for p in picks])
        counts: dict[str, int] = {}
        for p in picks:
            for wheel, n in p["lockups"].items():
                counts[wheel] = counts.get(wheel, 0) + n
        row["lockups"] = counts
        rows.append(row)
    lockups = [{**lock, "lap": lp["lap"]} for lp in ok for lock in lp["lockups"]]
    return {"available": True, "reason": None, "corners": rows, "lockups": lockups, "laps": len(ok)}


def relative_index(deg: float | None, phase: str) -> float | None:
    """The understeer index minus the typical value of its phase (0 = like the library's typical car)."""
    return None if deg is None else deg - NEUTRAL_DEG[phase]


def balance_label(deg: float | None, phase: str) -> str | None:
    """Words for an understeer index in a phase, relative to NEUTRAL_DEG."""
    deg = relative_index(deg, phase)
    if deg is None:
        return None
    if deg >= US_STRONG_DEG:
        return "understeer"
    if deg >= US_SLIGHT_DEG:
        return "slight understeer"
    if deg <= -US_STRONG_DEG:
        return "oversteer"
    if deg <= -US_SLIGHT_DEG:
        return "slight oversteer"
    return "neutral"


def balance_summary(rows: list[dict[str, Any]], corners: list[dict[str, Any]]) -> str:
    """One line: per phase the median balance over all corners (split by speed class where the classes disagree),
    plus the corners with strong oversteer, e.g. "Entry neutral · mid slight understeer in slow corners · exit
    neutral · oversteer on exit T3, T4"."""
    meta = {c["id"]: c for c in corners}
    parts: list[str] = []
    for phase in PHASES:
        overall = balance_label(_median([r[phase] for r in rows]), phase)
        if overall is None:
            continue
        by_class: dict[str, str] = {}
        for cls in ("slow", "medium", "fast"):
            label = balance_label(_median([r[phase] for r in rows if meta[r["id"]]["speed_class"] == cls]), phase)
            if label is not None:
                by_class[cls] = label
        if len(set(by_class.values())) <= 1:
            parts.append(f"{phase} {overall}")
        else:
            groups: dict[str, list[str]] = {}
            for cls, label in by_class.items():
                groups.setdefault(label, []).append(cls)
            parts.append(" / ".join(f"{phase} {label} in {' + '.join(cls)} corners" for label, cls in groups.items()))
    if not parts:
        return "Not enough cornering samples to say"
    text = " · ".join(parts)
    text = text[0].upper() + text[1:]
    for phase in PHASES:
        snaps = [meta[r["id"]]["name"] for r in rows if r[phase] is not None and relative_index(r[phase], phase) <= -US_STRONG_DEG]
        if snaps:
            text += f" · oversteer on {phase} {', '.join(snaps)}"
    return text
