"""Engineer tests and per-track settled setup values (the live engineer's memory)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS engineer_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    program TEXT NOT NULL,
    baseline_json TEXT NOT NULL,
    final_json TEXT NOT NULL,
    result_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS engineer_settled (
    track TEXT NOT NULL,
    param TEXT NOT NULL,
    value REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (track, param)
);
"""


def ensure_engineer_schema(app_root: Path | None = None) -> None:
    with connect(app_root) as conn:
        conn.executescript(SCHEMA)


def _iso(epoch: float | None) -> str | None:
    return None if epoch is None else datetime.fromtimestamp(float(epoch), timezone.utc).isoformat()


def save_test(result: dict[str, Any], app_root: Path | None = None) -> int:
    """Store one finished test (``Engineer.result()``) and upsert its newly settled values. Returns the row id."""
    ensure_engineer_schema(app_root)
    now = datetime.now(timezone.utc).isoformat()
    track = str(result["track"])
    with connect(app_root) as conn:
        cur = conn.execute(
            "INSERT INTO engineer_tests (track, started_at, finished_at, program, baseline_json, final_json, result_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (track, _iso(result.get("started_at")) or now, _iso(result.get("finished_at")), result["program"],
             json.dumps(result.get("baseline") or {}), json.dumps(result.get("final") or {}), json.dumps(result)))
        for param, value in (result.get("settled") or {}).items():
            conn.execute("INSERT OR REPLACE INTO engineer_settled (track, param, value, updated_at) VALUES (?, ?, ?, ?)",
                         (track, param, float(value), now))
        return int(cur.lastrowid)


def settled_for(track: str, app_root: Path | None = None) -> dict[str, float]:
    """Parameters already settled on this track, as ``{garage key: value}``."""
    ensure_engineer_schema(app_root)
    with connect(app_root) as conn:
        rows = conn.execute("SELECT param, value FROM engineer_settled WHERE track = ?", (track,)).fetchall()
    return {r["param"]: float(r["value"]) for r in rows}


def list_tests(track: str | None = None, app_root: Path | None = None) -> list[dict[str, Any]]:
    ensure_engineer_schema(app_root)
    with connect(app_root) as conn:
        rows = conn.execute("SELECT * FROM engineer_tests" + (" WHERE track = ?" if track else "") + " ORDER BY id DESC",
                            (track,) if track else ()).fetchall()
    return [{**dict(r), "result": json.loads(r["result_json"])} for r in rows]


def all_settled(app_root: Path | None = None) -> dict[str, dict[str, tuple[float, str]]]:
    """Every settled value in the library as ``{track: {garage key: (value, updated_at)}}``."""
    ensure_engineer_schema(app_root)
    with connect(app_root) as conn:
        rows = conn.execute("SELECT track, param, value, updated_at FROM engineer_settled").fetchall()
    out: dict[str, dict[str, tuple[float, str]]] = {}
    for r in rows:
        out.setdefault(r["track"], {})[r["param"]] = (float(r["value"]), str(r["updated_at"]))
    return out
