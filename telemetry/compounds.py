"""Tyre compounds: F1 game actualTyreCompound codes, C-numbers and per-track S/M/H allocation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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


def ensure_allocation_schema(app_root: Path | None = None) -> None:
    with connect(app_root) as conn:
        conn.executescript(ALLOCATION_SCHEMA)


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
    source: str  # "manual" | "inferred" | "none"

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
    if row:
        roles = {int(row[k]): r for k, r in (("soft", "S"), ("medium", "M"), ("hard", "H")) if row[k] is not None}
        return Allocation(track_n, roles, "manual")
    roles = roles_from_codes(track_compounds_seen(track_n, app_root))
    return Allocation(track_n, roles, "inferred" if roles else "none")


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
