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
"""


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
