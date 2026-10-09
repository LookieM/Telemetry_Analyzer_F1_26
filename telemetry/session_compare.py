"""Cross-session telemetry overlay (focus session vs reference / PB)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .corners import (
    analyze_lap_corners,
    compare_corners,
    normalize_track_name,
    resolve_corners,
)
from .db import ANALYSIS_COLUMNS, get_session, load_session_telemetry
from .metrics import align_laps, build_lap_summary, compute_time_delta, get_lap
from .progress import ensure_progress_schema, pb_history


@dataclass
class SessionCompareResult:
    focus_session: dict[str, Any]
    ref_session: dict[str, Any]
    focus_lap: int
    ref_lap: int
    focus_time: float
    ref_time: float
    aligned: pd.DataFrame
    corner_cmp: pd.DataFrame
    track: str | None
    track_length: float | None
    ref_is_pb: bool


def pb_reference_session(
    track: str,
    app_root: Path | None = None,
) -> dict[str, Any] | None:
    """Lifetime PB session row for a track (fastest personal_bests entry)."""
    ensure_progress_schema(app_root)
    track = normalize_track_name(track) or track
    history = pb_history(track, app_root)
    if history.empty:
        return None
    best = history.sort_values("lap_time", ascending=True).iloc[0]
    sid = best.get("session_id")
    if sid is None or (isinstance(sid, float) and pd.isna(sid)):
        return None
    session = get_session(int(sid), app_root)
    if not session:
        return None
    session = dict(session)
    session["_pb_lap"] = int(best["lap"]) if pd.notna(best.get("lap")) else session.get("best_lap")
    session["_pb_lap_time"] = float(best["lap_time"])
    return session


def _session_best_lap(session: dict[str, Any], summary: pd.DataFrame) -> int:
    if session.get("best_lap") is not None and not (
        isinstance(session["best_lap"], float) and pd.isna(session["best_lap"])
    ):
        return int(session["best_lap"])
    if not summary.empty and "is_best" in summary.columns:
        return int(summary.loc[summary["is_best"], "lap"].iloc[0])
    return int(summary["lap"].iloc[0])


def _track_length(session: dict[str, Any], df: pd.DataFrame) -> float | None:
    if session.get("track_length"):
        try:
            return float(session["track_length"])
        except (TypeError, ValueError):
            pass
    if "lap_distance" in df.columns and not df.empty:
        return float(df["lap_distance"].max())
    return None


def compare_sessions(
    focus_session_id: int,
    ref_session_id: int,
    *,
    focus_lap: int | None = None,
    ref_lap: int | None = None,
    app_root: Path | None = None,
) -> SessionCompareResult:
    """
    Align focus session lap onto reference session lap distance grid.

    Uses the same align_laps / compute_time_delta / compare_corners pipeline
    as within-session lap compare.
    """
    focus_session = get_session(focus_session_id, app_root)
    ref_session = get_session(ref_session_id, app_root)
    if not focus_session:
        raise FileNotFoundError(f"Focus session {focus_session_id} not found")
    if not ref_session:
        raise FileNotFoundError(f"Reference session {ref_session_id} not found")

    focus_df_all = load_session_telemetry(focus_session_id, app_root, columns=ANALYSIS_COLUMNS)
    ref_df_all = load_session_telemetry(ref_session_id, app_root, columns=ANALYSIS_COLUMNS)
    focus_summary = build_lap_summary(focus_df_all)
    ref_summary = build_lap_summary(ref_df_all)
    if focus_summary.empty or ref_summary.empty:
        raise ValueError("One or both sessions have no valid laps.")

    f_lap = focus_lap if focus_lap is not None else _session_best_lap(focus_session, focus_summary)
    # Prefer recorded PB lap when the reference session is the lifetime PB holder
    r_lap = ref_lap
    if r_lap is None:
        track_guess = normalize_track_name(
            focus_session.get("track") or ref_session.get("track")
        )
        pb = pb_reference_session(track_guess or "", app_root) if track_guess else None
        if pb and int(pb["id"]) == int(ref_session_id) and pb.get("_pb_lap") is not None:
            r_lap = int(pb["_pb_lap"])
        else:
            r_lap = _session_best_lap(ref_session, ref_summary)

    focus_lap_df = get_lap(focus_df_all, f_lap)
    ref_lap_df = get_lap(ref_df_all, r_lap)
    if focus_lap_df.empty or ref_lap_df.empty:
        raise ValueError("Selected laps have no telemetry samples.")

    aligned = compute_time_delta(align_laps(ref_lap_df, focus_lap_df))

    track = normalize_track_name(
        focus_session.get("track") or ref_session.get("track")
    )
    length = _track_length(focus_session, focus_df_all) or _track_length(ref_session, ref_df_all)
    corners = resolve_corners(track, length, focus_lap_df)
    focus_corners = analyze_lap_corners(focus_lap_df, track, length, corners=corners)
    ref_corners = analyze_lap_corners(ref_lap_df, track, length, corners=corners)
    corner_cmp = compare_corners(focus_corners, ref_corners)

    f_time = float(focus_summary.loc[focus_summary["lap"] == f_lap, "lap_time"].iloc[0])
    r_time = float(ref_summary.loc[ref_summary["lap"] == r_lap, "lap_time"].iloc[0])

    pb = pb_reference_session(track or "", app_root) if track else None
    ref_is_pb = bool(pb and int(pb["id"]) == int(ref_session_id))

    return SessionCompareResult(
        focus_session=dict(focus_session),
        ref_session=dict(ref_session),
        focus_lap=f_lap,
        ref_lap=r_lap,
        focus_time=f_time,
        ref_time=r_time,
        aligned=aligned,
        corner_cmp=corner_cmp,
        track=track,
        track_length=length,
        ref_is_pb=ref_is_pb,
    )


def session_label(session: dict[str, Any]) -> str:
    sid = session.get("id", "?")
    track = session.get("track") or "?"
    best = session.get("best_lap_time")
    tag = session.get("session_type") or ""
    tag_bit = f" [{tag}]" if tag else ""
    if best is not None and not (isinstance(best, float) and pd.isna(best)):
        t = float(best)
        m = int(t // 60)
        s = t - m * 60
        time_s = f"{m}:{s:06.3f}" if m else f"{s:.3f}s"
    else:
        time_s = "—"
    return f"#{sid}{tag_bit} · {track} · best {time_s}"
