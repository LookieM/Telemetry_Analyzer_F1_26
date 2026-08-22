"""Progress tracking: personal bests and track dossiers."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .corners import analyze_lap_corners, normalize_track_name
from .db import connect, get_session, load_session_telemetry
from .metrics import (
    MAX_VALID_LAP_S,
    MIN_VALID_LAP_S,
    build_lap_summary,
    get_lap,
    session_meta,
)

PROGRESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS personal_bests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track TEXT NOT NULL,
    lap_time REAL NOT NULL,
    session_id INTEGER,
    lap INTEGER,
    car TEXT,
    set_at TEXT NOT NULL,
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS corner_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    lap INTEGER NOT NULL,
    track TEXT NOT NULL,
    is_session_best INTEGER DEFAULT 0,
    corners_json TEXT NOT NULL,
    UNIQUE(session_id, lap)
);

CREATE TABLE IF NOT EXISTS track_goals (
    track TEXT PRIMARY KEY,
    target_lap_time REAL NOT NULL,
    updated_at TEXT NOT NULL,
    notes TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_pb_track ON personal_bests(track, lap_time);
CREATE INDEX IF NOT EXISTS idx_pb_set_at ON personal_bests(set_at);
"""


def ensure_progress_schema(app_root: Path | None = None) -> None:
    with connect(app_root) as conn:
        conn.executescript(PROGRESS_SCHEMA)


def scrub_improbable_lap_records(app_root: Path | None = None) -> dict[str, int]:
    """
    Remove takeback / red-flag short laps from PB history and fix session bests.

    Uses the same absolute time window as build_lap_summary (not distance —
    stored lap rows no longer have telemetry).
    """
    ensure_progress_schema(app_root)
    with connect(app_root) as conn:
        pb_removed = conn.execute(
            "DELETE FROM personal_bests WHERE lap_time < ? OR lap_time > ?",
            (MIN_VALID_LAP_S, MAX_VALID_LAP_S),
        ).rowcount

        bad_sessions = conn.execute(
            """
            SELECT id FROM sessions
            WHERE best_lap_time IS NOT NULL
              AND (best_lap_time < ? OR best_lap_time > ?)
            """,
            (MIN_VALID_LAP_S, MAX_VALID_LAP_S),
        ).fetchall()

        sessions_fixed = 0
        for row in bad_sessions:
            sid = int(row["id"])
            best = conn.execute(
                """
                SELECT lap, lap_time FROM laps
                WHERE session_id = ? AND lap_time >= ? AND lap_time <= ?
                ORDER BY lap_time ASC
                LIMIT 1
                """,
                (sid, MIN_VALID_LAP_S, MAX_VALID_LAP_S),
            ).fetchone()
            conn.execute("UPDATE laps SET is_best = 0 WHERE session_id = ?", (sid,))
            if best:
                best_lap = int(best["lap"])
                best_time = float(best["lap_time"])
                conn.execute(
                    "UPDATE sessions SET best_lap = ?, best_lap_time = ? WHERE id = ?",
                    (best_lap, best_time, sid),
                )
                conn.execute(
                    "UPDATE laps SET is_best = 1 WHERE session_id = ? AND lap = ?",
                    (sid, best_lap),
                )
                conn.execute(
                    "UPDATE laps SET delta_best = lap_time - ? WHERE session_id = ?",
                    (best_time, sid),
                )
            else:
                conn.execute(
                    "UPDATE sessions SET best_lap = NULL, best_lap_time = NULL WHERE id = ?",
                    (sid,),
                )
            sessions_fixed += 1

        laps_removed = conn.execute(
            "DELETE FROM laps WHERE lap_time < ? OR lap_time > ?",
            (MIN_VALID_LAP_S, MAX_VALID_LAP_S),
        ).rowcount

    return {
        "pb_removed": int(pb_removed or 0),
        "sessions_fixed": int(sessions_fixed),
        "laps_removed": int(laps_removed or 0),
    }


def _probable_times(series: pd.Series) -> pd.Series:
    t = series.dropna().astype(float)
    return t[(t >= MIN_VALID_LAP_S) & (t <= MAX_VALID_LAP_S)]


def record_session_progress(
    session_id: int,
    df: pd.DataFrame,
    summary: pd.DataFrame,
    app_root: Path | None = None,
    track_hint: str | None = None,
    car_hint: str | None = None,
    track_length_hint: float | None = None,
) -> dict[str, Any]:
    """Persist PB history + corner snapshot for the session best lap."""
    ensure_progress_schema(app_root)
    if summary.empty:
        return {"pb_updated": False}

    meta = session_meta(df)
    # Compact parquet may omit track/car — fall back to session row / hints
    session_row = get_session(session_id, app_root) or {}
    track = normalize_track_name(
        track_hint or meta.get("track") or session_row.get("track")
    )
    if not track:
        return {"pb_updated": False, "reason": "no track"}

    best_row = summary.loc[summary["is_best"]].iloc[0]
    best_lap = int(best_row["lap"])
    best_time = float(best_row["lap_time"])
    if best_time < MIN_VALID_LAP_S or best_time > MAX_VALID_LAP_S:
        return {"pb_updated": False, "reason": "improbable best"}
    car = car_hint or meta.get("car") or session_row.get("car")
    length = (
        track_length_hint
        or meta.get("track_length")
        or session_row.get("track_length")
        or (float(df["lap_distance"].max()) if "lap_distance" in df.columns else None)
    )
    now = datetime.now(timezone.utc).isoformat()

    lap_df = get_lap(df, best_lap)
    corners = analyze_lap_corners(lap_df, track, length)
    corners_payload = corners.to_dict(orient="records") if not corners.empty else []

    pb_updated = False
    with connect(app_root) as conn:
        conn.execute(
            """
            INSERT INTO corner_snapshots (session_id, lap, track, is_session_best, corners_json)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(session_id, lap) DO UPDATE SET
                corners_json = excluded.corners_json,
                is_session_best = 1,
                track = excluded.track
            """,
            (session_id, best_lap, track, json.dumps(corners_payload)),
        )

        current_pb = conn.execute(
            "SELECT lap_time FROM personal_bests WHERE track = ? ORDER BY lap_time ASC LIMIT 1",
            (track,),
        ).fetchone()
        is_new_pb = current_pb is None or best_time < float(current_pb["lap_time"]) - 1e-4
        if is_new_pb:
            conn.execute(
                """
                INSERT INTO personal_bests (track, lap_time, session_id, lap, car, set_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (track, best_time, session_id, best_lap, car, now, "auto"),
            )
            pb_updated = True

    return {
        "pb_updated": pb_updated,
        "track": track,
        "best_time": best_time,
        "best_lap": best_lap,
        "corners": len(corners_payload),
    }


def pb_history(track: str, app_root: Path | None = None) -> pd.DataFrame:
    ensure_progress_schema(app_root)
    track = normalize_track_name(track) or track
    with connect(app_root) as conn:
        rows = conn.execute(
            """
            SELECT id, track, lap_time, session_id, lap, car, set_at, notes
            FROM personal_bests
            WHERE track = ?
            ORDER BY set_at ASC
            """,
            (track,),
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame([dict(r) for r in rows])
    return out.loc[
        (out["lap_time"] >= MIN_VALID_LAP_S) & (out["lap_time"] <= MAX_VALID_LAP_S)
    ].reset_index(drop=True)


def set_track_goal(
    track: str,
    target_lap_time: float,
    notes: str = "",
    app_root: Path | None = None,
) -> None:
    ensure_progress_schema(app_root)
    track = normalize_track_name(track) or track
    now = datetime.now(timezone.utc).isoformat()
    with connect(app_root) as conn:
        conn.execute(
            """
            INSERT INTO track_goals (track, target_lap_time, updated_at, notes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(track) DO UPDATE SET
                target_lap_time = excluded.target_lap_time,
                updated_at = excluded.updated_at,
                notes = excluded.notes
            """,
            (track, float(target_lap_time), now, notes),
        )


def get_track_goal(track: str, app_root: Path | None = None) -> dict[str, Any] | None:
    ensure_progress_schema(app_root)
    track = normalize_track_name(track) or track
    with connect(app_root) as conn:
        row = conn.execute(
            "SELECT * FROM track_goals WHERE track = ?",
            (track,),
        ).fetchone()
    return dict(row) if row else None


def track_dossier(
    track: str,
    app_root: Path | None = None,
    session_type: str | None = None,
) -> dict[str, Any]:
    """Aggregate progress view for one circuit."""
    ensure_progress_schema(app_root)
    from .db import ensure_session_meta_schema

    ensure_session_meta_schema(app_root)
    track = normalize_track_name(track) or track

    clauses = ["track = ?"]
    params: list[Any] = [track]
    if session_type:
        clauses.append("session_type = ?")
        params.append(session_type)
    where = " AND ".join(clauses)

    with connect(app_root) as conn:
        sessions = conn.execute(
            f"""
            SELECT id, created_at, source_name, car, lap_count, best_lap, best_lap_time,
                   notes, stored_size_bytes, original_size_bytes,
                   session_type, conditions, setup_fingerprint, setup_json
            FROM sessions
            WHERE {where}
            ORDER BY created_at DESC
            """,
            params,
        ).fetchall()
        pb_rows = conn.execute(
            """
            SELECT lap_time, session_id, lap, car, set_at
            FROM personal_bests WHERE track = ?
            ORDER BY set_at ASC
            """,
            (track,),
        ).fetchall()
        goal = conn.execute(
            "SELECT * FROM track_goals WHERE track = ?",
            (track,),
        ).fetchone()
        latest_corners = conn.execute(
            """
            SELECT cs.corners_json, cs.session_id, cs.lap, s.best_lap_time, s.created_at
            FROM corner_snapshots cs
            JOIN sessions s ON s.id = cs.session_id
            WHERE cs.track = ? AND cs.is_session_best = 1
            ORDER BY s.created_at DESC
            LIMIT 1
            """,
            (track,),
        ).fetchone()

    session_df = pd.DataFrame([dict(r) for r in sessions]) if sessions else pd.DataFrame()
    history = pd.DataFrame([dict(r) for r in pb_rows]) if pb_rows else pd.DataFrame()

    if not history.empty and "lap_time" in history.columns:
        history = history.loc[
            (history["lap_time"] >= MIN_VALID_LAP_S) & (history["lap_time"] <= MAX_VALID_LAP_S)
        ].reset_index(drop=True)

    best_time = float(history["lap_time"].min()) if not history.empty else None
    if best_time is None and not session_df.empty and session_df["best_lap_time"].notna().any():
        valid_sess = _probable_times(session_df["best_lap_time"])
        best_time = float(valid_sess.min()) if not valid_sess.empty else None

    # Consistency from recent session bests (probable times only)
    recent = session_df.head(8) if not session_df.empty else pd.DataFrame()
    consistency = None
    if not recent.empty and recent["best_lap_time"].notna().sum() >= 1:
        times = _probable_times(recent["best_lap_time"])
        if len(times) >= 2:
            consistency = {
                "mean": float(times.mean()),
                "std": float(times.std(ddof=0)),
                "spread": float(times.max() - times.min()),
                "n": int(len(times)),
            }

    corners = []
    if latest_corners and latest_corners["corners_json"]:
        try:
            corners = json.loads(latest_corners["corners_json"])
        except json.JSONDecodeError:
            corners = []

    # Compare latest session-best corners vs lifetime PB session corners if available
    corner_trend = pd.DataFrame()
    if not history.empty and len(history) >= 1:
        pb_session = int(history.sort_values("lap_time").iloc[0]["session_id"])
        with connect(app_root) as conn:
            pb_corners_row = conn.execute(
                """
                SELECT corners_json FROM corner_snapshots
                WHERE session_id = ? AND is_session_best = 1
                LIMIT 1
                """,
                (pb_session,),
            ).fetchone()
        if pb_corners_row and latest_corners and latest_corners["session_id"] != pb_session:
            try:
                pb_c = pd.DataFrame(json.loads(pb_corners_row["corners_json"]))
                last_c = pd.DataFrame(corners)
                if not pb_c.empty and not last_c.empty:
                    corner_trend = last_c.merge(
                        pb_c[["corner_id", "time_s"]].rename(columns={"time_s": "pb_time_s"}),
                        on="corner_id",
                        how="left",
                    )
                    corner_trend["delta_vs_pb"] = corner_trend["time_s"] - corner_trend["pb_time_s"]
            except Exception:
                corner_trend = pd.DataFrame()

    from .setup_history import setup_timeline

    timeline = setup_timeline(track, app_root, session_type=session_type)

    pb_session_id = None
    if not history.empty:
        pb_session_id = int(history.sort_values("lap_time").iloc[0]["session_id"])

    return {
        "track": track,
        "sessions": session_df,
        "pb_history": history,
        "best_time": best_time,
        "goal": dict(goal) if goal else None,
        "consistency": consistency,
        "latest_corners": corners,
        "corner_trend": corner_trend,
        "session_count": int(len(session_df)),
        "setup_timeline": timeline,
        "pb_session_id": pb_session_id,
        "session_type_filter": session_type,
    }


def backfill_progress_from_library(app_root: Path | None = None) -> int:
    """Compute PB/corners for sessions that predate the progress tables."""
    ensure_progress_schema(app_root)
    from .db import list_sessions

    sessions = list_sessions(app_root)
    if sessions.empty:
        return 0
    # Oldest first so PB history progresses chronologically
    sessions = sessions.sort_values("created_at")
    updated = 0
    for _, row in sessions.iterrows():
        sid = int(row["id"])
        try:
            df = load_session_telemetry(sid, app_root)
            summary = build_lap_summary(df, track_length=row.get("track_length"))
            result = record_session_progress(
                sid,
                df,
                summary,
                app_root,
                track_hint=row.get("track"),
                car_hint=row.get("car"),
                track_length_hint=row.get("track_length"),
            )
            if result.get("track"):
                updated += 1
        except Exception:
            continue
    return updated
