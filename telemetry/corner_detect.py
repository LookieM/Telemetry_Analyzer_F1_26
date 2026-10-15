"""Detect the corners of a track from one reference lap (pure: no I/O, no UI).

A corner is a stretch of the lap without sustained full throttle that holds a real speed minimum:
it starts where braking begins or the throttle first lifts below 95 % and ends where full throttle
returns. Two minima with no full throttle between them are therefore one corner (a complex); a
speed dip of < 3 km/h without braking is a flat kink, not a corner.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

FULL_THROTTLE = 0.95  # throttle at / above this counts as full throttle
BRAKE_ON = 0.05  # brake above this interrupts full throttle
BRAKE_REAL = 0.10  # brake above this is a real brake application
MIN_FULL_RUN_M = 40  # full throttle shorter than this does not separate two corners
MIN_DIP_KMH = 6.0  # minimum speed prominence of a corner without braking
MIN_CORNER_M = 20  # shortest believable corner
SLOW_BELOW_KMH = 120.0
FAST_ABOVE_KMH = 200.0
NAME_TOLERANCE_M = 120.0  # how far a catalogue apex may lie outside a corner and still name it
MINIMA_HALF_WINDOW_M = 25
EDGE_M = 15  # a speed minimum this close to the lap's first / last sample is cut by the line

NEEDED_COLUMNS = ("lap_distance", "speed", "throttle", "brake")


def speed_class(vmin_kmh: float) -> str:
    if vmin_kmh < SLOW_BELOW_KMH:
        return "slow"
    return "fast" if vmin_kmh > FAST_ABOVE_KMH else "medium"


def lap_grid(lap: pd.DataFrame, step: float = 1.0) -> dict[str, np.ndarray]:
    """The lap's speed / throttle / brake interpolated on a regular distance grid (default 1 m)."""
    missing = [c for c in NEEDED_COLUMNS if c not in lap.columns]
    if missing:
        raise ValueError(f"Lap frame lacks {', '.join(missing)}")
    frame = lap.sort_values("lap_distance").drop_duplicates(subset=["lap_distance"], keep="last")
    x = frame["lap_distance"].to_numpy(dtype=float)
    if len(x) < 10:
        raise ValueError("Lap frame too short")
    d = np.arange(np.ceil(x[0]), np.floor(x[-1]) + 1e-9, step)
    out = {"d": d}
    for name in ("speed", "throttle", "brake"):
        out[name] = np.interp(d, x, np.nan_to_num(frame[name].to_numpy(dtype=float)))
    return out


def _smooth(a: np.ndarray, n: int = 5) -> np.ndarray:
    pad = np.pad(a, n // 2, mode="edge")
    return np.convolve(pad, np.ones(n) / n, mode="valid")


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) of every True run."""
    if not mask.size:
        return []
    edges = np.flatnonzero(np.diff(np.concatenate(([0], mask.astype(np.int8), [0]))))
    return [(int(a), int(b)) for a, b in zip(edges[0::2], edges[1::2])]


def full_throttle_mask(throttle: np.ndarray, brake: np.ndarray, step: float = 1.0) -> np.ndarray:
    """True where the car is on sustained full throttle (>= MIN_FULL_RUN_M of it, not braking)."""
    raw = (throttle >= FULL_THROTTLE) & (brake < BRAKE_ON)
    out = np.zeros_like(raw)
    for a, b in _runs(raw):
        if (b - a) * step >= MIN_FULL_RUN_M:
            out[a:b] = True
    return out


def _minima(v: np.ndarray) -> list[tuple[int, float]]:
    """(index, prominence) of every local speed minimum (plateaus count once)."""
    w = MINIMA_HALF_WINDOW_M
    out = []
    for i in range(1, len(v) - 1):
        lo, hi = max(0, i - w), min(len(v), i + w + 1)
        if v[i] > v[lo:hi].min() or (i > 0 and v[i] == v[i - 1]):
            continue
        a = i
        while a > 0 and v[a - 1] >= v[i]:
            a -= 1
        b = i
        while b < len(v) - 1 and v[b + 1] >= v[i]:
            b += 1
        left = v[a : i + 1].max() if a < i else v[i]
        right = v[i : b + 1].max() if b > i else v[i]
        out.append((i, float(min(left, right) - v[i])))
    return out


def _catalogue_spans(catalogue: Sequence[dict[str, Any]], length: float) -> list[tuple[str, str, float, float, float]]:
    """(id, name, position_m, from_m, to_m) of every catalogue corner: its apex (or the middle of its window)
    and, when it has no apex, the window it is known to lie in (from == to == apex otherwise)."""
    out = []
    for c in catalogue:
        if c.get("kind", "corner") == "straight":
            continue
        a, b = float(c["start_frac"]) * length, float(c["end_frac"]) * length
        if c.get("apex_frac") is not None:
            pos = float(c["apex_frac"]) * length
            out.append((str(c["id"]), str(c["name"]), pos, pos, pos))
        else:
            out.append((str(c["id"]), str(c["name"]), 0.5 * (a + b), a, b))
    return out


def _joined_name(entries: list[tuple[str, str]]) -> str:
    """One catalogue entry keeps its name; several become a turn range (T2–T5) or a joined list."""
    if len(entries) == 1:
        return entries[0][1]
    numbers: list[int] = []
    for cid, _ in entries:
        if not re.fullmatch(r"T\d+(-\d+)?", cid):
            return "–".join(name for _, name in entries)
        nums = [int(n) for n in re.findall(r"\d+", cid)]
        numbers += [nums[0], nums[-1]]
    return f"T{min(numbers)}–T{max(numbers)}"


def name_corners(corners: list[dict[str, Any]], catalogue: Sequence[dict[str, Any]] | None, length: float) -> None:
    """Name corners in place: catalogue entries go to the nearest corner window (within the tolerance);
    corners no entry reaches stay T1..Tn without a catalogue (unknown track) or C<n> inside one."""
    for i, c in enumerate(corners):
        c["name"] = f"T{i + 1}" if not catalogue else f"C{i + 1}"
    if not catalogue:
        return
    taken: dict[int, list[tuple[float, str, str]]] = {}
    for cid, name, pos, lo, hi in _catalogue_spans(catalogue, length):
        best, best_key = None, (NAME_TOLERANCE_M + 1, 0.0)
        for i, c in enumerate(corners):
            gap = max(0.0, c["start_m"] - hi, lo - c["end_m"])  # distance between the two spans (0 = they overlap)
            key = (gap, abs(0.5 * (c["start_m"] + c["end_m"]) - pos))
            if key < best_key:
                best, best_key = i, key
        if best is not None and best_key[0] <= NAME_TOLERANCE_M:
            taken.setdefault(best, []).append((pos, cid, name))
    for i, hits in taken.items():
        hits.sort()
        corners[i]["name"] = _joined_name([(cid, name) for _, cid, name in hits])


def detect_corners(
    lap: pd.DataFrame,
    catalogue: Sequence[dict[str, Any]] | None = None,
    track_length: float | None = None,
) -> list[dict[str, Any]]:
    """Ordered corners `{id, name, start_m, end_m, apex_m, vmin_kmh, speed_class, merged_from}` of a lap frame
    (lap_distance, speed, throttle, brake). `catalogue` is the track's TRACK_CORNERS_FRAC entry (optional)."""
    g = lap_grid(lap)
    d, thr, brk = g["d"], g["throttle"], g["brake"]
    v = _smooth(g["speed"])
    minima = _minima(v)
    full = full_throttle_mask(thr, brk)
    corners: list[dict[str, Any]] = []
    for a, b in _runs(~full):
        inside = [(i, p) for i, p in minima if a <= i < b]
        braked = bool((brk[a:b] > BRAKE_REAL).any())
        real = [(i, p) for i, p in inside if p >= MIN_DIP_KMH or braked]
        if not real and braked and b - a >= MIN_CORNER_M:
            real = [(a + int(np.argmin(v[a:b])), 0.0)]  # braking into the line / out of the data: still a corner
        if not real or d[b - 1] - d[a] < MIN_CORNER_M:
            continue
        apex = a + int(np.argmin(v[a:b]))
        if apex < EDGE_M or apex > len(d) - 1 - EDGE_M:
            continue  # the minimum sits on the start / finish line: only half a corner is in this lap
        corners.append(
            {
                "id": len(corners) + 1,
                "name": "",
                "start_m": float(d[a]),
                "end_m": float(d[b - 1]),
                "apex_m": float(d[apex]),
                "vmin_kmh": float(v[apex]),
                "speed_class": speed_class(float(v[apex])),
                "merged_from": [float(d[i]) for i, _ in real] if len(real) > 1 else [],
            }
        )
    length = float(track_length) if track_length else float(d[-1])
    name_corners(corners, catalogue, length)
    return corners
