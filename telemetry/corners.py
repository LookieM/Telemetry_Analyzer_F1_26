"""Named corner definitions and per-corner time analysis."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .track_catalog import (
    TRACK_ALIASES,
    TRACK_CORNERS_FRAC,
    TRACK_LENGTHS_M,
    catalog_track_names,
)


@dataclass
class CornerDef:
    id: str
    name: str
    start: float
    end: float
    kind: str
    apex: float | None = None


def normalize_track_name(track: str | None) -> str | None:
    if not track:
        return None
    t = str(track).strip()
    if t in TRACK_CORNERS_FRAC:
        return t
    return TRACK_ALIASES.get(t.lower(), t)


def list_supported_tracks() -> list[str]:
    return catalog_track_names()


def get_corners(track: str | None, track_length: float | None = None) -> list[CornerDef]:
    key = normalize_track_name(track)
    raw = TRACK_CORNERS_FRAC.get(key or "", [])
    if not raw:
        return []

    length = float(track_length) if track_length else float(TRACK_LENGTHS_M.get(key or "", 5000))
    out: list[CornerDef] = []
    for i, c in enumerate(raw):
        start = float(c["start_frac"]) * length
        end = float(c["end_frac"]) * length
        if i == len(raw) - 1:
            end = length
        apex = c.get("apex_frac")
        out.append(
            CornerDef(
                id=c["id"],
                name=c["name"],
                start=start,
                end=end,
                kind=c.get("kind", "corner"),
                apex=(float(apex) * length) if apex is not None else None,
            )
        )
    return out


def detect_corners_from_lap(lap_df: pd.DataFrame, min_gap_m: float = 90.0) -> list[CornerDef]:
    """
    Build generic T1..Tn segments from braking / speed valleys when the track
    is not in the catalog yet. Good enough for time-loss tables on new circuits.
    """
    if lap_df.empty or "lap_distance" not in lap_df.columns or "speed" not in lap_df.columns:
        return []

    lap = lap_df.sort_values("lap_distance")
    dist = lap["lap_distance"].to_numpy(dtype=float)
    spd = lap["speed"].to_numpy(dtype=float)
    brake = lap["brake"].to_numpy(dtype=float) if "brake" in lap.columns else np.zeros_like(spd)
    length = float(dist.max()) if len(dist) else 0.0
    if length < 100:
        return []

    sm = np.convolve(spd, np.ones(11) / 11, mode="same")
    valleys: list[tuple[float, float]] = []
    for i in range(40, len(sm) - 40):
        win = sm[i - 25 : i + 26]
        if sm[i] > win.min() + 1e-6:
            continue
        if sm[i] >= 240:
            continue
        recent_brake = brake[max(0, i - 100) : i + 1].max() > 0.2
        if not recent_brake and sm[i] > 180:
            continue
        d = float(dist[i])
        if not valleys or d - valleys[-1][0] >= min_gap_m:
            valleys.append((d, float(sm[i])))

    if len(valleys) < 2:
        return [
            CornerDef("SF", "Start/Finish", 0.0, length * 0.08, "straight"),
            CornerDef("Lap", "Full lap", length * 0.08, length, "corner"),
        ]

    bounds = [0.0]
    for i, (d, _) in enumerate(valleys):
        prev = valleys[i - 1][0] if i else 0.0
        nxt = valleys[i + 1][0] if i + 1 < len(valleys) else length
        start = (prev + d) / 2 if i else max(0.0, d - 120)
        end = (d + nxt) / 2
        bounds.append(start)
        bounds.append(end)
    # Rebuild clean contiguous segments from apex midpoints
    edges = [0.0]
    for i in range(len(valleys)):
        if i == 0:
            edges.append(max(valleys[0][0] - 100, length * 0.05))
        else:
            edges.append((valleys[i - 1][0] + valleys[i][0]) / 2)
    edges.append(length)
    # unique sorted
    edges = sorted(set(round(e, 1) for e in edges))
    if edges[0] != 0:
        edges = [0.0] + edges
    if edges[-1] < length:
        edges.append(length)

    out: list[CornerDef] = [
        CornerDef("SF", "Start/Finish", edges[0], edges[1], "straight")
    ]
    for i in range(1, len(edges) - 1):
        # find nearest valley inside segment for apex
        seg_a, seg_b = edges[i], edges[i + 1]
        apex = None
        for d, _ in valleys:
            if seg_a <= d <= seg_b:
                apex = d
                break
        out.append(
            CornerDef(
                id=f"T{i}",
                name=f"T{i}",
                start=seg_a,
                end=seg_b,
                kind="corner",
                apex=apex,
            )
        )
    return out


def resolve_corners(
    track: str | None,
    track_length: float | None = None,
    lap_df: pd.DataFrame | None = None,
) -> list[CornerDef]:
    """Prefer catalog names; otherwise auto-detect from a reference lap."""
    corners = get_corners(track, track_length)
    if corners:
        return corners
    if lap_df is not None:
        return detect_corners_from_lap(lap_df)
    return []


def corner_at_distance(
    track: str | None,
    distance: float,
    track_length: float | None = None,
    corners: list[CornerDef] | None = None,
) -> CornerDef | None:
    items = corners if corners is not None else get_corners(track, track_length)
    if not items:
        return None
    for c in items:
        if c.start <= distance < c.end:
            return c
    last = items[-1]
    if distance <= last.end:
        return last
    return None


def _segment_time(lap_df: pd.DataFrame, start: float, end: float) -> float | None:
    if lap_df.empty or "lap_distance" not in lap_df.columns or "lap_time" not in lap_df.columns:
        return None
    d = lap_df["lap_distance"].to_numpy(dtype=float)
    t = lap_df["lap_time"].to_numpy(dtype=float)
    if len(d) < 2:
        return None
    t0 = float(np.interp(start, d, t))
    t1 = float(np.interp(min(end, float(d.max())), d, t))
    dt = t1 - t0
    return dt if dt > 0 else None


def analyze_lap_corners(
    lap_df: pd.DataFrame,
    track: str | None,
    track_length: float | None = None,
    corners: list[CornerDef] | None = None,
) -> pd.DataFrame:
    """Return one row per corner/segment for a single lap."""
    items = corners if corners is not None else resolve_corners(track, track_length, lap_df)
    if not items:
        return pd.DataFrame()

    rows = []
    for c in items:
        mask = (lap_df["lap_distance"] >= c.start) & (lap_df["lap_distance"] < c.end)
        chunk = lap_df.loc[mask]
        time_s = _segment_time(lap_df, c.start, c.end)
        row = {
            "corner_id": c.id,
            "corner_name": c.name,
            "kind": c.kind,
            "start_m": c.start,
            "end_m": c.end,
            "apex_m": c.apex,
            "time_s": time_s,
        }
        if not chunk.empty and "speed" in chunk.columns:
            row["vmin"] = float(chunk["speed"].min())
            row["vmax"] = float(chunk["speed"].max())
        if not chunk.empty and "brake" in chunk.columns:
            row["brake_max"] = float(chunk["brake"].max())
        if not chunk.empty and "throttle" in chunk.columns:
            row["throttle_avg"] = float(chunk["throttle"].mean())
        rows.append(row)
    return pd.DataFrame(rows)


def compare_corners(focus: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """Merge two corner tables; positive delta_s => focus slower."""
    if focus.empty:
        return pd.DataFrame()
    if reference.empty:
        out = focus.copy()
        out["ref_time_s"] = np.nan
        out["delta_s"] = np.nan
        return out
    merged = focus.merge(
        reference[["corner_id", "time_s", "vmin"]].rename(
            columns={"time_s": "ref_time_s", "vmin": "ref_vmin"}
        ),
        on="corner_id",
        how="left",
    )
    merged["delta_s"] = merged["time_s"] - merged["ref_time_s"]
    if "vmin" in merged.columns and "ref_vmin" in merged.columns:
        merged["delta_vmin"] = merged["vmin"] - merged["ref_vmin"]
    return merged


def corner_loss_summary(compared: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    if compared.empty or "delta_s" not in compared.columns:
        return pd.DataFrame()
    corners_only = compared[compared["kind"] == "corner"].copy()
    return corners_only.sort_values("delta_s", ascending=False).head(top_n)
