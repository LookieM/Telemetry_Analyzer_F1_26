"""Tyre compounds: F1 game actualTyreCompound codes, C-numbers and per-track S/M/H allocation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .corners import normalize_track_name
from .db import connect

# F1 UDP m_actualTyreCompound (F1 25/26): 16=C5 ... 20=C1, 21=C0, 22=C6, 7=inter, 8=wet.
ACTUAL_COMPOUNDS: dict[int, str] = {
    22: "C6",
    16: "C5",
    17: "C4",
    18: "C3",
    19: "C2",
    20: "C1",
    21: "C0",
    7: "Inter",
    8: "Wet",
}
# Higher = softer. Wets sit outside the slick scale.
_SOFTNESS = {22: 6, 16: 5, 17: 4, 18: 3, 19: 2, 20: 1, 21: 0}
WET_CODES = frozenset({7, 8})
SLICK_CODES = frozenset(_SOFTNESS)

ROLE_COLORS = {"S": "#D7263D", "M": "#E8A317", "H": "#8A9099", "Inter": "#2E9E44", "Wet": "#1F6FD1"}
# Fallback when the S/M/H allocation of a track is unknown: softer = warmer.
_C_COLORS = {6: "#B5179E", 5: "#D7263D", 4: "#E8A317", 3: "#8A9099", 2: "#5C6670", 1: "#3A4148", 0: "#24292E"}

ALLOCATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS track_tyre_allocation (
    track TEXT PRIMARY KEY,
    soft INTEGER,
    medium INTEGER,
    hard INTEGER,
    updated_at TEXT NOT NULL
);
"""


GAME_TYRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS track_game_tyres (
    track TEXT PRIMARY KEY,
    soft INTEGER,
    medium INTEGER,
    hard INTEGER,
    sets_json TEXT NOT NULL,
    total_laps INTEGER,
    session_type TEXT,
    updated_at TEXT NOT NULL
);
"""
# visualTyreCompound -> role (the game's own S / M / H marking)
VISUAL_ROLES = {16: "S", 17: "M", 18: "H"}


def ensure_allocation_schema(app_root: Path | None = None) -> None:
    with connect(app_root) as conn:
        conn.executescript(ALLOCATION_SCHEMA)
        conn.executescript(GAME_TYRES_SCHEMA)


def c_label(code: int | None) -> str:
    if code is None or int(code) < 0:
        return "—"
    return ACTUAL_COMPOUNDS.get(int(code), f"#{int(code)}")


def is_slick(code: int | None) -> bool:
    return code is not None and int(code) in SLICK_CODES


def softness(code: int) -> int:
    return _SOFTNESS.get(int(code), -1)


@dataclass(frozen=True)
class Allocation:
    track: str
    roles: dict[int, str]  # compound code -> "S" | "M" | "H"
    source: str  # "manual" | "game" | "inferred" | "pirelli-2026" | "none"

    def role(self, code: int | None) -> str | None:
        if code is None:
            return None
        if int(code) in WET_CODES:
            return ACTUAL_COMPOUNDS[int(code)]
        return self.roles.get(int(code))

    def label(self, code: int | None) -> str:
        role = self.role(code)
        base = c_label(code)
        return f"{base} ({role})" if role and role not in ("Inter", "Wet") else base

    def color(self, code: int | None) -> str:
        role = self.role(code)
        if role in ROLE_COLORS:
            return ROLE_COLORS[role]
        return _C_COLORS.get(softness(code) if code is not None else -1, "#8A9099")


def roles_from_codes(codes: list[int]) -> dict[int, str]:
    """Up to three dry compounds, softest first, become S / M / H."""
    slicks = sorted({int(c) for c in codes if is_slick(c)}, key=softness, reverse=True)
    if not slicks or len(slicks) > 3:
        return {}
    if len(slicks) == 3:
        return dict(zip(slicks, ("S", "M", "H")))
    if len(slicks) == 2 and softness(slicks[0]) - softness(slicks[1]) == 2:
        # e.g. C5 + C3 seen: the nomination is C3-C5 and the unseen middle one is the medium.
        middle = next(c for c, s in _SOFTNESS.items() if s == softness(slicks[0]) - 1)
        return {slicks[0]: "S", middle: "M", slicks[1]: "H"}
    if len(slicks) == 2 and softness(slicks[0]) - softness(slicks[1]) == 1 and softness(slicks[0]) == max(_SOFTNESS.values()):
        # e.g. C6 + C5 seen: nothing is softer than C6, so the third (unseen) compound is the harder C4.
        harder = next(c for c, s in _SOFTNESS.items() if s == softness(slicks[1]) - 1)
        return {slicks[0]: "S", slicks[1]: "M", harder: "H"}
    # Adjacent pair (or a single compound): assume the softest seen is the soft.
    return dict(zip(slicks, ("S", "M")))


def track_compounds_seen(track: str, app_root: Path | None = None) -> list[int]:
    """Compound codes logged on any lap of any library session on this track."""
    from .setup_history import list_track_sessions

    sessions = list_track_sessions(track, app_root)
    if sessions.empty:
        return []
    ids = [int(i) for i in sessions["id"].tolist()]
    marks = ",".join("?" * len(ids))
    with connect(app_root) as conn:
        rows = conn.execute(
            f"SELECT DISTINCT compound FROM laps WHERE session_id IN ({marks}) AND compound >= 0", ids
        ).fetchall()
    return sorted(int(r["compound"]) for r in rows if r["compound"] is not None)


def get_allocation(track: str | None, app_root: Path | None = None) -> Allocation:
    track_n = normalize_track_name(track) or (track or "")
    if not track_n:
        return Allocation("", {}, "none")
    ensure_allocation_schema(app_root)
    with connect(app_root) as conn:
        row = conn.execute("SELECT * FROM track_tyre_allocation WHERE track = ?", (track_n,)).fetchone()
        game = conn.execute("SELECT * FROM track_game_tyres WHERE track = ?", (track_n,)).fetchone()
    # Priority: your own setting > what the game reported (TyreSets) > what the library saw >
    # the real-world 2026 Pirelli nomination (provisional) > nothing.
    for src, rec in (("manual", row), ("game", game)):
        if rec:
            roles = {int(rec[k]): r for k, r in (("soft", "S"), ("medium", "M"), ("hard", "H")) if rec[k] is not None}
            if roles:
                return Allocation(track_n, roles, src)
    from .track_catalog import PIRELLI_2026

    roles = roles_from_codes(track_compounds_seen(track_n, app_root))
    seed = dict(zip(PIRELLI_2026.get(track_n, ()), ("S", "M", "H")))
    # One or two compounds seen leave the set incomplete: the nomination fills it when it agrees.
    if roles and (len(roles) == 3 or not seed or not set(roles) <= set(seed)):
        return Allocation(track_n, roles, "inferred")
    if seed:
        return Allocation(track_n, seed, "pirelli-2026")
    return Allocation(track_n, {}, "none")


def save_game_tyres(
    track: str,
    sets: list[dict[str, Any]],
    *,
    total_laps: int | None = None,
    session_type: str = "",
    app_root: Path | None = None,
) -> dict[int, dict[str, Any]] | None:
    """Store the dry allocation and per-compound game data from a TyreSets packet.

    ``sets``: dicts with ``actual``, ``visual``, ``life`` (usable life, laps) and ``delta_ms``
    (game lap-time delta vs the fitted set). Returns the per-compound summary, or None when the
    packet does not show three dry compounds.
    """
    track_n = normalize_track_name(track) or track
    by_code: dict[int, dict[str, Any]] = {}
    for s in sets:
        actual, visual = int(s["actual"]), int(s["visual"])
        if actual in by_code or actual == 0:
            continue
        by_code[actual] = {"role": VISUAL_ROLES.get(visual) or ACTUAL_COMPOUNDS.get(actual), "life": int(s["life"]),
                           "delta_ms": int(s["delta_ms"])}
    roles = {c: d["role"] for c, d in by_code.items() if d["role"] in ("S", "M", "H")}
    if len(roles) != 3:
        return None
    inv = {r: c for c, r in roles.items()}
    ensure_allocation_schema(app_root)
    with connect(app_root) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO track_game_tyres (track, soft, medium, hard, sets_json, total_laps, session_type, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (track_n, inv["S"], inv["M"], inv["H"], json.dumps({str(k): v for k, v in by_code.items()}),
             int(total_laps) if total_laps else None, session_type, datetime.now(timezone.utc).isoformat()),
        )
    return by_code


def get_game_tyres(track: str | None, app_root: Path | None = None) -> dict[str, Any] | None:
    """What the game reported for this track: {"compounds": {code: {role, life, delta_ms}}, "total_laps", ...}."""
    track_n = normalize_track_name(track) or (track or "")
    if not track_n:
        return None
    ensure_allocation_schema(app_root)
    with connect(app_root) as conn:
        row = conn.execute("SELECT * FROM track_game_tyres WHERE track = ?", (track_n,)).fetchone()
    if not row:
        return None
    return {
        "track": track_n,
        "compounds": {int(k): v for k, v in json.loads(row["sets_json"]).items()},
        "total_laps": row["total_laps"],
        "session_type": row["session_type"],
        "updated_at": row["updated_at"],
    }


def set_allocation(
    track: str,
    soft: int | None,
    medium: int | None,
    hard: int | None,
    app_root: Path | None = None,
) -> None:
    track_n = normalize_track_name(track) or track
    ensure_allocation_schema(app_root)
    with connect(app_root) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO track_tyre_allocation (track, soft, medium, hard, updated_at) VALUES (?, ?, ?, ?, ?)",
            (track_n, soft, medium, hard, datetime.now(timezone.utc).isoformat()),
        )


def clear_allocation(track: str, app_root: Path | None = None) -> None:
    ensure_allocation_schema(app_root)
    with connect(app_root) as conn:
        conn.execute("DELETE FROM track_tyre_allocation WHERE track = ?", (normalize_track_name(track) or track,))
