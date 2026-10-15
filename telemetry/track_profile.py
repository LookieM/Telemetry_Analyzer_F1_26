"""Track profile: a small vector describing a circuit, used to judge how alike two tracks are.

Fields (all fractions are shares of the lap distance):
    slow_frac / medium_frac / fast_frac  distance inside slow (<120 km/h apex) / medium / fast (>200 km/h) corners
    full_throttle_frac                   distance at sustained full throttle
    heavy_braking_zones                  corners entered more than HEAVY_BRAKING_KMH above their apex speed
    lap_length_m, source ("driven" | "catalogue"), track, reverse_of (forward layout name or None)

A driven profile comes from the track's stored corners (plus, when a lap frame is at hand, the real full-throttle
mask and entry speeds). A catalogue profile is estimated from the catalogue's corner zones and calibrated against
the driven profiles (see the CAL_* constants)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import db
from .corner_detect import full_throttle_mask, lap_grid
from .corner_store import FRAME_COLUMNS, NoCleanLap, ensure_track_corners
from .corners import normalize_track_name
from .metrics import get_lap
from .track_catalog import TRACK_CORNERS_FRAC, TRACK_LENGTHS_M

HEAVY_BRAKING_KMH = 100.0  # entry speed - apex speed above this is a heavy braking zone
ENTRY_LOOKBACK_M = 20.0  # entry speed = top speed from this far before the corner window to its apex
PROXY_HEAVY_VMIN_KMH = 150.0  # without a lap frame: corners slower than this count as heavy braking zones

REVERSE_SUFFIX = " Reverse"

# Catalogue estimate, calibrated on the 11 catalogue layouts driven in the library (least squares, n=11):
#   total corner share  = CAL_CORNER_BASE + CAL_CORNER_PER_SEG_KM * (catalogue corner zones per km)   r=0.70
#   full-throttle share = CAL_FT_BASE + CAL_FT_PER_SEG_KM * (catalogue corner zones per km)           r=-0.67
# the corner share is split slow / medium / fast by CAL_CLASS_MIX (pooled driven mix); heavy braking zones are the
# driven mean (zone count does not predict it, r=0.12). Madring has no catalogue zones and gets the mean estimate.
CAL_CORNER_BASE = 0.193
CAL_CORNER_PER_SEG_KM = 0.0957
CAL_FT_BASE = 0.794
CAL_FT_PER_SEG_KM = -0.0916
CAL_CLASS_MIX = (0.562, 0.370, 0.068)  # slow, medium, fast share of corner distance
CAL_HEAVY_ZONES = 5
CAL_CORNER_CLAMP = (0.12, 0.60)
CAL_FT_CLAMP = (0.40, 0.78)

# Similarity: exp(-distance), distance = sqrt(mean(((a-b)/scale)^2)) over these fields.
SIMILARITY_SCALES: dict[str, float] = {
    "slow_frac": 0.10,
    "medium_frac": 0.10,
    "fast_frac": 0.08,
    "full_throttle_frac": 0.10,
    "heavy_braking_zones": 3.0,
    "lap_length_m": 1200.0,
}
REVERSE_PENALTY = 0.9  # similarity factor between a reverse layout and its forward layout
CATALOGUE_PENALTY = 1.0  # extra factor per catalogue-estimated side (estimates are noisier); 1 = none


def forward_name(track: str | None) -> str | None:
    if track and track.endswith(REVERSE_SUFFIX):
        return track[: -len(REVERSE_SUFFIX)]
    return None


def _empty(track: str | None, source: str, length: float) -> dict[str, Any]:
    return {"track": track, "source": source, "lap_length_m": float(length), "reverse_of": forward_name(track)}


def _entry_speeds(corners: list[dict[str, Any]], d: np.ndarray, v: np.ndarray) -> list[float]:
    out = []
    for c in corners:
        lo = np.searchsorted(d, c["start_m"] - ENTRY_LOOKBACK_M)
        hi = np.searchsorted(d, c["apex_m"]) + 1
        seg = v[lo:max(hi, lo + 1)]
        out.append(float(seg.max()) if seg.size else float(c["vmin_kmh"]))
    return out


def profile_from_corners(
    corners: list[dict[str, Any]],
    lap_length_m: float,
    full_throttle_m: float | None = None,
    lap: pd.DataFrame | None = None,
    track: str | None = None,
) -> dict[str, Any]:
    """Profile of stored corners. `full_throttle_m` = metres at full throttle (else the distance outside the
    corners is the proxy; `lap`, a frame with lap_distance/speed/throttle/brake, supplies both the real
    full-throttle distance and the corner entry speeds, otherwise heavy zones are counted by apex speed)."""
    length = float(lap_length_m)
    if length <= 0:
        raise ValueError("Lap length must be positive")
    metres = {"slow": 0.0, "medium": 0.0, "fast": 0.0}
    for c in corners:
        metres[c.get("speed_class", "medium")] += max(0.0, float(c["end_m"]) - float(c["start_m"]))
    entries: list[float] | None = None
    heavy_estimated = True
    if lap is not None:
        try:
            g = lap_grid(lap)
            mask = full_throttle_mask(g["throttle"], g["brake"])
            full_throttle_m = float(mask.sum())  # 1 m grid
            entries = _entry_speeds(corners, g["d"], g["speed"])
            heavy_estimated = False
        except ValueError:
            pass
    if entries is not None:
        heavy = sum(1 for c, e in zip(corners, entries) if e - float(c["vmin_kmh"]) > HEAVY_BRAKING_KMH)
    else:
        heavy = sum(1 for c in corners if float(c["vmin_kmh"]) < PROXY_HEAVY_VMIN_KMH)
    in_corners = sum(metres.values())
    ft = float(full_throttle_m) if full_throttle_m is not None else max(0.0, length - in_corners)
    p = _empty(track, "driven", length)
    p.update(
        slow_frac=metres["slow"] / length,
        medium_frac=metres["medium"] / length,
        fast_frac=metres["fast"] / length,
        full_throttle_frac=min(1.0, ft / length),
        heavy_braking_zones=int(heavy),
        heavy_braking_estimated=heavy_estimated,
        corner_count=len(corners),
    )
    return p


def _reverse_segments(segs: list[dict]) -> list[dict]:
    return [{**s, "start_frac": 1 - s["end_frac"], "end_frac": 1 - s["start_frac"]} for s in reversed(segs)]


def _catalogue_segments(track: str) -> list[dict] | None:
    if track in TRACK_CORNERS_FRAC:
        return TRACK_CORNERS_FRAC[track]
    fwd = forward_name(track)
    if fwd and fwd in TRACK_CORNERS_FRAC:
        return _reverse_segments(TRACK_CORNERS_FRAC[fwd])
    return None


def _catalogue_features(track: str) -> dict[str, float] | None:
    segs = _catalogue_segments(track)
    if not segs:
        return None
    length_km = TRACK_LENGTHS_M[track] / 1000.0
    corner = [s for s in segs if s.get("kind", "corner") != "straight"]
    straight_share = sum(s["end_frac"] - s["start_frac"] for s in segs if s.get("kind") == "straight")
    return {
        "segments": float(len(corner)),
        "segments_per_km": len(corner) / length_km,
        "straight_share": straight_share,
        "mean_width": float(np.mean([s["end_frac"] - s["start_frac"] for s in corner])),
    }


def _estimate(track: str) -> dict[str, Any] | None:
    f = _catalogue_features(track)
    if f is None:
        return None
    corner = float(np.clip(CAL_CORNER_BASE + CAL_CORNER_PER_SEG_KM * f["segments_per_km"], *CAL_CORNER_CLAMP))
    ft = float(np.clip(CAL_FT_BASE + CAL_FT_PER_SEG_KM * f["segments_per_km"], *CAL_FT_CLAMP))
    slow, med, fast = (corner * m for m in CAL_CLASS_MIX)
    p = _empty(track, "catalogue", TRACK_LENGTHS_M[track])
    p.update(
        slow_frac=slow,
        medium_frac=med,
        fast_frac=fast,
        full_throttle_frac=ft,
        heavy_braking_zones=CAL_HEAVY_ZONES,
        heavy_braking_estimated=True,
        corner_count=int(f["segments"]),
    )
    return p


PROFILE_FIELDS = ("slow_frac", "medium_frac", "fast_frac", "full_throttle_frac", "heavy_braking_zones")


def profile_from_catalogue(track: str) -> dict[str, Any]:
    """Estimated profile of any catalogue layout (reverse layouts mirror the forward zones; a layout without
    corner zones, Madring, gets the mean of the others with its own length). Raises KeyError off-catalogue."""
    track = normalize_track_name(track)
    if track not in TRACK_LENGTHS_M:
        raise KeyError(f"{track!r} is not in the track catalogue")
    est = _estimate(track)
    if est is not None:
        return est
    others = [e for t in TRACK_LENGTHS_M if (e := _estimate(t)) is not None]
    p = _empty(track, "catalogue", TRACK_LENGTHS_M[track])
    for k in ("slow_frac", "medium_frac", "fast_frac", "full_throttle_frac"):
        p[k] = float(np.mean([o[k] for o in others]))
    p["heavy_braking_zones"] = int(round(np.mean([o["heavy_braking_zones"] for o in others])))
    p["heavy_braking_estimated"] = True
    p["corner_count"] = int(round(np.mean([o["corner_count"] for o in others])))
    return p


def _source_lap_frame(stored: dict[str, Any], root: Path) -> pd.DataFrame | None:
    sid, lap = stored.get("source_session"), stored.get("source_lap")
    if sid is None or lap is None:
        return None
    try:
        df = db.load_session_telemetry(int(sid), root, columns=FRAME_COLUMNS)
        frame = get_lap(df, int(lap))
    except (FileNotFoundError, KeyError, ValueError):
        return None
    return frame if len(frame) else None


def track_profile(track: str, root: Path) -> dict[str, Any]:
    """Driven profile when the track has (or can build, via its best clean lap) stored corners, else catalogue."""
    name = normalize_track_name(track)
    try:
        stored = ensure_track_corners(name, root)
    except (NoCleanLap, ValueError, LookupError):
        stored = None
    if stored and stored.get("corners"):
        frame = _source_lap_frame(stored, root)
        length = float(frame["lap_distance"].max()) if frame is not None else None
        length = length or TRACK_LENGTHS_M.get(name) or max(float(c["end_m"]) for c in stored["corners"])
        return profile_from_corners(stored["corners"], length, lap=frame, track=name)
    return profile_from_catalogue(name)


def distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    sq = [((float(a[k]) - float(b[k])) / s) ** 2 for k, s in SIMILARITY_SCALES.items()]
    return math.sqrt(sum(sq) / len(sq))


def similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    """exp(-distance) over the standardised profile fields, in (0, 1]; 1 for identical profiles. A layout and
    its reverse are compared like any pair but scaled by REVERSE_PENALTY."""
    s = math.exp(-distance(a, b))
    ta, tb = a.get("track"), b.get("track")
    if ta and tb and ta != tb and (forward_name(ta) == tb or forward_name(tb) == ta):
        s *= REVERSE_PENALTY
    for p in (a, b):
        if p.get("source") == "catalogue":
            s *= CATALOGUE_PENALTY
    return s
