"""Setup-duel storage: names for setups (by mechanical fingerprint, per track) and the duels that were run."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS setup_names (
    fingerprint TEXT NOT NULL,
    track TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (fingerprint, track)
);

CREATE TABLE IF NOT EXISTS duels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    result_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS track_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track TEXT NOT NULL,
    setup_json TEXT NOT NULL,
    fingerprint TEXT,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    ref_id INTEGER,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_track_baselines_track ON track_baselines (track, active);
"""

BASELINE_SOURCES = ("duel", "engineer", "manual", "library", "generator")


def ensure_duel_schema(app_root: Path | None = None) -> None:
    with connect(app_root) as conn:
        conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_names(track: str, app_root: Path | None = None) -> dict[str, str]:
    ensure_duel_schema(app_root)
    with connect(app_root) as conn:
        rows = conn.execute("SELECT fingerprint, name FROM setup_names WHERE track = ?", (track,)).fetchall()
    return {r["fingerprint"]: r["name"] for r in rows}


def set_name(fingerprint: str, track: str, name: str, app_root: Path | None = None, source: str = "manual") -> str | None:
    """Store a setup's name; an empty name removes it. Returns the stored name."""
    ensure_duel_schema(app_root)
    name = name.strip()
    with connect(app_root) as conn:
        if not name:
            conn.execute("DELETE FROM setup_names WHERE fingerprint = ? AND track = ?", (fingerprint, track))
            return None
        conn.execute(
            "INSERT OR REPLACE INTO setup_names (fingerprint, track, name, source, updated_at) VALUES (?, ?, ?, ?, ?)",
            (fingerprint, track, name, source, _now()),
        )
    return name


def save_duel(track: str, mode: str, result: dict[str, Any], app_root: Path | None = None) -> int:
    ensure_duel_schema(app_root)
    with connect(app_root) as conn:
        cur = conn.execute(
            "INSERT INTO duels (track, mode, started_at, result_json) VALUES (?, ?, ?, ?)",
            (track, mode, _now(), json.dumps(result, default=float)),
        )
        return int(cur.lastrowid)


def get_duel(duel_id: int, app_root: Path | None = None) -> dict[str, Any] | None:
    ensure_duel_schema(app_root)
    with connect(app_root) as conn:
        row = conn.execute("SELECT * FROM duels WHERE id = ?", (duel_id,)).fetchone()
    if not row:
        return None
    return {"id": row["id"], "track": row["track"], "mode": row["mode"], "started_at": row["started_at"], "result": json.loads(row["result_json"])}


def list_duels(app_root: Path | None = None) -> list[dict[str, Any]]:
    """Every stored duel, newest first (same shape as ``get_duel``)."""
    ensure_duel_schema(app_root)
    with connect(app_root) as conn:
        rows = conn.execute("SELECT * FROM duels ORDER BY id DESC").fetchall()
    return [{"id": r["id"], "track": r["track"], "mode": r["mode"], "started_at": r["started_at"], "result": json.loads(r["result_json"])} for r in rows]


# --------------------------------------------------------------------------- track baselines


def _baseline_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"], "track": row["track"], "setup": json.loads(row["setup_json"]), "fingerprint": row["fingerprint"],
        "name": row["name"], "source": row["source"], "ref_id": row["ref_id"], "meta": json.loads(row["meta_json"] or "{}"),
        "created_at": row["created_at"], "active": bool(row["active"]),
    }


def set_baseline(track: str, setup: dict[str, Any], *, source: str, name: str, fingerprint: str | None = None,
                 ref_id: int | None = None, meta: dict[str, Any] | None = None, app_root: Path | None = None) -> dict[str, Any]:
    """Store a new baseline for the track and make it the only active one (older rows stay as history)."""
    if source not in BASELINE_SOURCES:
        raise ValueError(f"unknown baseline source {source!r}")
    ensure_duel_schema(app_root)
    with connect(app_root) as conn:
        conn.execute("UPDATE track_baselines SET active = 0 WHERE track = ?", (track,))
        cur = conn.execute(
            "INSERT INTO track_baselines (track, setup_json, fingerprint, name, source, ref_id, meta_json, created_at, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (track, json.dumps(setup, default=float), fingerprint, name, source, ref_id, json.dumps(meta or {}, default=float), _now()),
        )
        row = conn.execute("SELECT * FROM track_baselines WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _baseline_row(row)


def restore_baseline(track: str, baseline_id: int, app_root: Path | None = None) -> dict[str, Any] | None:
    """Re-activate an older row of this track; None when it does not exist (or belongs to another track)."""
    ensure_duel_schema(app_root)
    with connect(app_root) as conn:
        row = conn.execute("SELECT * FROM track_baselines WHERE id = ? AND track = ?", (baseline_id, track)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE track_baselines SET active = 0 WHERE track = ?", (track,))
        conn.execute("UPDATE track_baselines SET active = 1 WHERE id = ?", (baseline_id,))
        row = conn.execute("SELECT * FROM track_baselines WHERE id = ?", (baseline_id,)).fetchone()
    return _baseline_row(row)


def get_baselines(track: str, app_root: Path | None = None) -> dict[str, Any]:
    """``{active: row | None, history: [rows newest first, active included]}``."""
    ensure_duel_schema(app_root)
    with connect(app_root) as conn:
        rows = conn.execute("SELECT * FROM track_baselines WHERE track = ? ORDER BY id DESC", (track,)).fetchall()
    items = [_baseline_row(r) for r in rows]
    return {"active": next((i for i in items if i["active"]), None), "history": items}
