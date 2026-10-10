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
    if t in TRACK_CORNERS_FRAC or t in TRACK_LENGTHS_M:
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


# Phase metric columns produced by analyze_lap_corners (beyond time / vmin).
PHASE_METRIC_COLS = (
    "brake_point_m",
    "peak_brake_m",
    "brake_release_m",
    "turn_in_speed",
    "vmin",
    "vmin_m",
    "exit_speed",
    "throttle_on_m",
    "trail_brake_s",
    "entry_time_s",
    "mid_time_s",
    "exit_time_s",
)


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


def _first_crossing(dist: np.ndarray, signal: np.ndarray, threshold: float, rising: bool = True) -> float | None:
    """Distance of first sample that crosses threshold (rising or falling)."""
    if len(dist) < 2:
        return None
    if rising:
        above = signal >= threshold
        if not above.any():
            return None
        # Prefer first rising edge if prior samples exist below threshold
        idx = int(np.argmax(above))
        if idx > 0 and signal[idx - 1] < threshold:
            return float(dist[idx])
        if idx == 0 and above[0]:
            # Already above at window start — still report start as onset
            return float(dist[0])
        return float(dist[idx])
    below = signal <= threshold
    if not below.any():
        return None
    idx = int(np.argmax(below))
    return float(dist[idx])


def _interp_at(dist: np.ndarray, values: np.ndarray, at: float) -> float | None:
    if len(dist) < 2:
        return None
    if at < float(dist.min()) or at > float(dist.max()):
        return None
    return float(np.interp(at, dist, values))


def _corner_phase_metrics(lap_df: pd.DataFrame, corner: CornerDef) -> dict:
    """
    Entry / mid / exit kinematics for one corner segment.

    Distances are lap_distance (m). Speeds are km/h. trail_brake_s is seconds.
    """
    out: dict = {}
    if lap_df.empty or "lap_distance" not in lap_df.columns:
        return out

    # Approach window: slightly before segment start so brake markers are captured
    lookback = min(180.0, max(40.0, (corner.end - corner.start) * 0.45))
    win_start = max(0.0, corner.start - lookback)
    mask = (lap_df["lap_distance"] >= win_start) & (lap_df["lap_distance"] < corner.end)
    win = lap_df.loc[mask].sort_values("lap_distance")
    if win.empty:
        return out

    dist = win["lap_distance"].to_numpy(dtype=float)
    spd = win["speed"].to_numpy(dtype=float) if "speed" in win.columns else np.full(len(dist), np.nan)
    brk = win["brake"].to_numpy(dtype=float) if "brake" in win.columns else np.zeros(len(dist))
    thr = win["throttle"].to_numpy(dtype=float) if "throttle" in win.columns else np.zeros(len(dist))
    has_time = "lap_time" in win.columns
    t = win["lap_time"].to_numpy(dtype=float) if has_time else np.arange(len(dist), dtype=float) * 0.02

    # Lateral / steer cues for turn-in (optional)
    if "g_lat" in win.columns:
        lat = np.abs(win["g_lat"].to_numpy(dtype=float))
    elif "steering" in win.columns:
        lat = np.abs(win["steering"].to_numpy(dtype=float))
    else:
        lat = np.zeros(len(dist))

    # --- Brake point: first heavy brake while still relatively fast ---
    brake_point = None
    peak_brake_m = None
    brake_release = None
    if np.isfinite(brk).any() and brk.max() > 0.25:
        # Prefer onset inside approach→apex where speed was high recently
        heavy = brk >= 0.35
        if heavy.any():
            # Rising edge search from window start
            for i in range(1, len(brk)):
                if brk[i] >= 0.35 and brk[i - 1] < 0.28 and (not np.isfinite(spd[i]) or spd[i] > 80):
                    brake_point = float(dist[i])
                    break
            if brake_point is None:
                brake_point = _first_crossing(dist, brk, 0.35, rising=True)

            peak_i = int(np.nanargmax(brk))
            peak_brake_m = float(dist[peak_i])

            # Release: after peak, brake drops below 0.12
            after = slice(peak_i, len(brk))
            rel = _first_crossing(dist[after], brk[after], 0.12, rising=False)
            if rel is not None:
                brake_release = rel

    out["brake_point_m"] = brake_point
    out["peak_brake_m"] = peak_brake_m
    out["brake_release_m"] = brake_release

    # --- Min speed / apex distance inside the corner segment ---
    seg_mask = (dist >= corner.start) & (dist < corner.end)
    if seg_mask.any() and np.isfinite(spd[seg_mask]).any():
        seg_spd = spd.copy()
        seg_spd[~seg_mask] = np.nan
        vmin_i = int(np.nanargmin(seg_spd))
        out["vmin"] = float(spd[vmin_i])
        out["vmin_m"] = float(dist[vmin_i])
    elif np.isfinite(spd).any():
        vmin_i = int(np.nanargmin(spd))
        out["vmin"] = float(spd[vmin_i])
        out["vmin_m"] = float(dist[vmin_i])
    else:
        vmin_i = None

    apex_m = corner.apex if corner.apex is not None else out.get("vmin_m")

    # --- Turn-in: first significant lateral load after brake onset (or segment start) ---
    turn_in_m = None
    search_from = brake_point if brake_point is not None else corner.start
    after_brake = dist >= search_from
    if after_brake.any() and lat.max() > 0.15:
        lat_cut = max(0.55, float(np.nanpercentile(lat[lat > 0], 55)) * 0.55) if (lat > 0).any() else 0.8
        sub_d, sub_lat = dist[after_brake], lat[after_brake]
        turn_in_m = _first_crossing(sub_d, sub_lat, lat_cut, rising=True)
    if turn_in_m is None and brake_release is not None:
        turn_in_m = brake_release
    if turn_in_m is None and apex_m is not None:
        turn_in_m = float(apex_m) - min(40.0, (corner.end - corner.start) * 0.25)

    if turn_in_m is not None and np.isfinite(spd).any():
        out["turn_in_speed"] = _interp_at(dist, spd, turn_in_m)
    out["turn_in_m"] = turn_in_m

    # --- Throttle-on: first meaningful throttle after min-speed / apex ---
    throttle_on = None
    pivot = out.get("vmin_m", apex_m)
    if pivot is None:
        pivot = corner.start + (corner.end - corner.start) * 0.4
    after_pivot = dist >= float(pivot)
    if after_pivot.any():
        throttle_on = _first_crossing(dist[after_pivot], thr[after_pivot], 0.35, rising=True)
        if throttle_on is None:
            throttle_on = _first_crossing(dist[after_pivot], thr[after_pivot], 0.20, rising=True)
    out["throttle_on_m"] = throttle_on

    # --- Exit speed: near segment end / once mostly back on power ---
    exit_probe = corner.end - min(15.0, (corner.end - corner.start) * 0.08)
    if throttle_on is not None:
        exit_probe = max(exit_probe, float(throttle_on) + 5.0)
    exit_probe = min(exit_probe, float(dist.max()))
    out["exit_speed"] = _interp_at(dist, spd, exit_probe)

    # --- Trail-brake duration: brake still applied after turn-in until release ---
    trail_s = None
    if turn_in_m is not None and has_time:
        tb_mask = (dist >= turn_in_m) & (brk >= 0.12) & (thr < 0.45)
        if apex_m is not None:
            tb_mask &= dist <= float(apex_m) + 25.0
        if tb_mask.any():
            trail_s = float(t[tb_mask][-1] - t[tb_mask][0])
            if trail_s < 0:
                trail_s = None
    out["trail_brake_s"] = trail_s

    # --- Entry / mid / exit phase times (distance thirds or brake→vmin→exit) ---
    if has_time:
        entry_a = brake_point if brake_point is not None else corner.start
        mid_a = out.get("vmin_m", apex_m) or (corner.start + corner.end) / 2
        exit_a = throttle_on if throttle_on is not None else mid_a
        exit_b = corner.end
        out["entry_time_s"] = _segment_time(lap_df, float(entry_a), float(mid_a))
        out["mid_time_s"] = _segment_time(lap_df, float(mid_a), float(exit_a)) if exit_a > mid_a else 0.0
        out["exit_time_s"] = _segment_time(lap_df, float(exit_a), float(exit_b))

    return out


def analyze_lap_corners(
    lap_df: pd.DataFrame,
    track: str | None,
    track_length: float | None = None,
    corners: list[CornerDef] | None = None,
) -> pd.DataFrame:
    """Return one row per corner/segment for a single lap (incl. phase metrics)."""
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

        if c.kind != "straight":
            phase = _corner_phase_metrics(lap_df, c)
            # Phase vmin may refine the chunk min; prefer phase values when present
            for k, v in phase.items():
                if v is not None:
                    row[k] = v
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

    ref_cols = ["corner_id"]
    rename = {}
    for col in ("time_s", *PHASE_METRIC_COLS):
        if col in reference.columns and col not in ref_cols:
            ref_cols.append(col)
            rename[col] = f"ref_{col}"

    merged = focus.merge(
        reference[ref_cols].rename(columns=rename),
        on="corner_id",
        how="left",
    )
    if "time_s" in merged.columns and "ref_time_s" in merged.columns:
        merged["delta_s"] = merged["time_s"] - merged["ref_time_s"]

    # Signed deltas: focus − reference (positive brake_point => later marker)
    for col in PHASE_METRIC_COLS:
        ref_col = f"ref_{col}"
        if col in merged.columns and ref_col in merged.columns:
            merged[f"delta_{col}"] = merged[col] - merged[ref_col]
    return merged


def corner_loss_summary(compared: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    if compared.empty or "delta_s" not in compared.columns:
        return pd.DataFrame()
    corners_only = compared[compared["kind"] == "corner"].copy()
    return corners_only.sort_values("delta_s", ascending=False).head(top_n)
