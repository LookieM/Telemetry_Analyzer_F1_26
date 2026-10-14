"""One-off library upkeep: re-read every session's garage setup from its stored telemetry."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .db import connect, db_path, default_data_dir, ensure_session_meta_schema, load_session_telemetry
from .garage import garage_from_raw, is_raw_setup
from .loader import SETUP_CHANNEL_KEYS, setup_from_telemetry
from .setup_history import compute_setup_fingerprint, parse_setup_json

FLAG = "setup_reread_v1"


def _backup_db(app_root: Path | None, label: str) -> Path:
    """Consistent copy of the library database into data/backups/<timestamp>-<label>/."""
    dest = default_data_dir(app_root) / "backups" / f"{datetime.now():%Y%m%d-%H%M%S}-{label}"
    dest.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(db_path(app_root)))
    dst = sqlite3.connect(str(dest / "telemetry.db"))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return dest


def reread_library_setups(app_root: Path | None = None) -> dict[str, Any]:
    """
    Re-derive each session's setup_json and setup fingerprint with the garage reader (earlier versions
    read rear camber / toe / springs from the front-right slot and clipped radians into degree ranges).
    The database is backed up first; sessions whose telemetry has no setup channels (or no parquet)
    keep their stored setup (a stored dict of raw channels is converted to garage units; the rear slots
    that were never kept stay unknown rather than guessed). Runs once: completion is recorded in the `library_meta` table.

    Returns ``{"done", "repaired", "kept", "backup"}``; ``done`` is False when already re-read.
    """
    ensure_session_meta_schema(app_root)
    with connect(app_root) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS library_meta (key TEXT PRIMARY KEY, value TEXT)")
        if conn.execute("SELECT 1 FROM library_meta WHERE key = ?", (FLAG,)).fetchone():
            return {"done": False, "repaired": 0, "kept": 0, "backup": None}
        rows = conn.execute("SELECT id, best_lap, setup_json FROM sessions").fetchall()
    backup = _backup_db(app_root, "before-setup-reread") if rows else None
    columns = [*SETUP_CHANNEL_KEYS, "lap", "tyre_compound_0"]
    repaired = kept = 0
    for row in rows:
        sid = int(row["id"])
        stored = parse_setup_json(row["setup_json"])
        setup: dict[str, float] = {}
        try:
            df = load_session_telemetry(sid, app_root, columns=columns)
            setup = setup_from_telemetry(df, int(row["best_lap"]) if row["best_lap"] is not None else None)
        except (FileNotFoundError, ValueError, OSError):
            pass
        if not setup and is_raw_setup(stored):
            setup = garage_from_raw(stored)  # legacy raw channels stored as the setup: unit and wheel fix only
        if not setup:
            kept += 1
            continue
        with connect(app_root) as conn:
            conn.execute(
                "UPDATE sessions SET setup_json = ?, setup_fingerprint = ? WHERE id = ?",
                (json.dumps(setup), compute_setup_fingerprint(setup), sid),
            )
        repaired += 1
    with connect(app_root) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO library_meta (key, value) VALUES (?, ?)",
            (FLAG, datetime.now().isoformat(timespec="seconds")),
        )
    return {"done": True, "repaired": repaired, "kept": kept, "backup": str(backup) if backup else None}
