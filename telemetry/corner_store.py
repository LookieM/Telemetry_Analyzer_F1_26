"""Per-track corner storage: corners are detected once from the track's best clean lap in the library and kept
in the `track_corners` table, so every session of a track shares the same corner windows."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import db
from .corner_detect import detect_corners
from .corners import normalize_track_name
from .metrics import build_lap_summary, get_lap
from .track_catalog import TRACK_CORNERS_FRAC, TRACK_LENGTHS_M

FRAME_COLUMNS = (*db.ANALYSIS_COLUMNS, "lap_distance", "lap_time", "speed", "throttle", "brake")
FULL_LAP_SHARE = 0.985  # a lap shorter than this share of the session's typical lap is cut and cannot define corners


class NoCleanLap(LookupError):
    """The track has no clean lap in the library to build corners from."""


def clean_laps(df: pd.DataFrame) -> pd.DataFrame:
    """Lap summary rows of the full-length clean ("push") laps of a session frame, fastest first."""
    summary = build_lap_summary(df)
    if summary.empty:
        return summary
    push = summary[summary["lap_class"] == "push"]
    lengths = {int(r.lap): float(get_lap(df, int(r.lap))["lap_distance"].max()) for r in push.itertuples()}
    if not lengths:
        return push
    typical = float(np.median(list(lengths.values())))
    keep = push["lap"].map(lambda lap: lengths[int(lap)] >= FULL_LAP_SHARE * typical)
    return push[keep].sort_values("lap_time")


def track_sessions(track: str, root: Path) -> list[dict[str, Any]]:
    sessions = db.list_sessions(root)
    if sessions.empty:
        return []
    return [r for r in sessions.to_dict("records") if normalize_track_name(r.get("track")) == track]


def best_clean_lap(track: str, root: Path) -> tuple[int, int] | None:
    """(session id, lap) of the fastest clean lap of the track in the whole library."""
    best: tuple[float, int, int] | None = None
    for s in track_sessions(track, root):
        try:
            df = db.load_session_telemetry(int(s["id"]), root, columns=FRAME_COLUMNS)
        except FileNotFoundError:
            continue
        if "lap_distance" not in df.columns:
            continue
        laps = clean_laps(df)
        if laps.empty:
            continue
        row = laps.iloc[0]
        if best is None or float(row["lap_time"]) < best[0]:
            best = (float(row["lap_time"]), int(s["id"]), int(row["lap"]))
    return (best[1], best[2]) if best else None


def get_track_corners(track: str, root: Path) -> dict[str, Any] | None:
    with db.connect(root) as conn:
        row = conn.execute("SELECT * FROM track_corners WHERE track = ?", (track,)).fetchone()
    if not row:
        return None
    return {
        "track": row["track"],
        "corners": json.loads(row["corners_json"]),
        "source_session": row["source_session_id"],
        "source_lap": row["source_lap"],
        "built_at": row["built_at"],
    }


def build_track_corners(track: str, session_id: int, lap: int, root: Path) -> dict[str, Any]:
    """Detect the corners of one given lap and store them for the track (replacing any earlier set)."""
    df = db.load_session_telemetry(session_id, root, columns=FRAME_COLUMNS)
    frame = get_lap(df, lap)
    if frame.empty:
        raise LookupError(f"Lap {lap} not found in session {session_id}")
    corners = detect_corners(frame, TRACK_CORNERS_FRAC.get(track), TRACK_LENGTHS_M.get(track))
    if not corners:
        raise ValueError(f"No corners found in lap {lap} of session {session_id}")
    built_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.connect(root) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO track_corners (track, corners_json, source_session_id, source_lap, built_at) VALUES (?, ?, ?, ?, ?)",
            (track, json.dumps(corners), session_id, lap, built_at),
        )
    return {"track": track, "corners": corners, "source_session": session_id, "source_lap": lap, "built_at": built_at}


def ensure_track_corners(track: str, root: Path) -> dict[str, Any]:
    """The stored corners of a track; built from its best clean lap the first time (NoCleanLap when there is none)."""
    stored = get_track_corners(track, root)
    if stored:
        return stored
    best = best_clean_lap(track, root)
    if best is None:
        raise NoCleanLap(f"No clean lap of {track} in the library to build corners from")
    return build_track_corners(track, best[0], best[1], root)
