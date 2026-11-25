"""The tyre sets you have on a track: the game's TyreSets snapshot (or your own list).

One row per track, the latest one wins: the live engine refreshes it whenever the game's sets
change (so after qualifying the planner sees what Q left), and the Planner can replace it by hand.
A set is ``{"compound": actual code, "wear": %, "available": bool, "fitted": bool}``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .corners import normalize_track_name
from .db import connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS tyre_inventory (
    track TEXT PRIMARY KEY,
    sets_json TEXT NOT NULL,
    source TEXT NOT NULL,
    session_type TEXT,
    updated_at TEXT NOT NULL
);
"""

SOURCES = ("game", "manual")


def _track(track: str | None) -> str:
    return normalize_track_name(track) or (track or "")


def ensure_schema(app_root: Path | None = None) -> None:
    with connect(app_root) as conn:
        conn.executescript(SCHEMA)


def clean_sets(sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Valid sets only (a real compound code), with wear clamped to 0..100."""
    out = []
    for s in sets:
        code = int(s.get("compound") or 0)
        if code <= 0:
            continue
        out.append({
            "compound": code,
            "wear": max(0.0, min(100.0, float(s.get("wear") or 0.0))),
            "available": bool(s.get("available", True)),
            "fitted": bool(s.get("fitted", False)),
        })
    return out


def save_inventory(
    track: str,
    sets: list[dict[str, Any]],
    *,
    source: str = "game",
    session_type: str | None = None,
    app_root: Path | None = None,
) -> None:
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}")
    ensure_schema(app_root)
    with connect(app_root) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tyre_inventory (track, sets_json, source, session_type, updated_at) VALUES (?, ?, ?, ?, ?)",
            (_track(track), json.dumps(clean_sets(sets)), source, session_type,
             datetime.now(timezone.utc).isoformat()),
        )


def get_inventory(track: str | None, app_root: Path | None = None) -> dict[str, Any] | None:
    """{"track", "sets", "source", "session_type", "updated_at"} or None when nothing is known."""
    t = _track(track)
    if not t:
        return None
    ensure_schema(app_root)
    with connect(app_root) as conn:
        row = conn.execute("SELECT * FROM tyre_inventory WHERE track = ?", (t,)).fetchone()
    if not row:
        return None
    return {"track": t, "sets": json.loads(row["sets_json"]), "source": row["source"],
            "session_type": row["session_type"], "updated_at": row["updated_at"]}


def clear_inventory(track: str, app_root: Path | None = None) -> None:
    ensure_schema(app_root)
    with connect(app_root) as conn:
        conn.execute("DELETE FROM tyre_inventory WHERE track = ?", (_track(track),))


def available_wear(sets: list[dict[str, Any]], *, exclude_fitted: bool = False) -> dict[int, list[float]]:
    """{compound: [wear % of each available set, freshest first]}."""
    out: dict[int, list[float]] = {}
    for s in clean_sets(sets):
        if not s["available"] or (exclude_fitted and s["fitted"]):
            continue
        out.setdefault(s["compound"], []).append(s["wear"])
    return {c: sorted(w) for c, w in out.items()}
