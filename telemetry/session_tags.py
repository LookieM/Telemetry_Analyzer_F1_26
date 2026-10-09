"""Infer a session's type (Race / Quali / FP) and track state from its file name and telemetry."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .conditions import compose_conditions
from .db import connect, list_sessions

# Tokens in SRT export names, e.g. "Austria_race.csv", "Monza_Q3.csv", "Montreal_SQ1.csv", "Catalunya_FP2.csv".
_TYPE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(race|gp|sprint|feature)", "Race"),
    (r"(s?q[123]?|quali\w*|qualifying|shootout)", "Quali"),
    (r"(fp1|p1)", "FP1"),
    (r"(fp2|p2)", "FP2"),
    (r"(fp3|p3)", "FP3"),
    (r"(practice|fp|free)", "FP1"),
    (r"(test|testing|tt|timetrial)", "Test"),
)
# Shares of laps on wet-weather tyres that set the track state.
WET_SHARE = 0.5
DAMP_SHARE = 0.15
RAIN_WEATHER = 3  # F1 UDP weather >= 3 is rain
RAIN_SHARE = 0.3


def _tokens(name: str) -> list[str]:
    stem = Path(name).stem.lower()
    return [t for t in re.split(r"[^a-z0-9]+", stem) if t]


def type_from_name(source_name: str | None) -> str:
    for token in _tokens(source_name or ""):
        for pattern, tag in _TYPE_PATTERNS:
            if re.fullmatch(pattern, token):
                return tag
    return ""


def type_from_laps(summary: pd.DataFrame) -> str:
    """A standing start followed by a long run of laps is a race."""
    if summary.empty or "lap_class" not in summary.columns:
        return ""
    if (summary["lap_class"] == "start").any() and len(summary) >= 8:
        return "Race"
    return ""


def state_from_telemetry(summary: pd.DataFrame, source_name: str | None = None) -> str:
    """dry / damp / inter / wet from the tyres run (laps), the game's weather, then the file name."""
    if not summary.empty and "compound" in summary.columns:
        comp = pd.to_numeric(summary["compound"], errors="coerce")
        comp = comp[comp >= 0]
        if len(comp):
            wet, inter = float((comp == 8).mean()), float((comp == 7).mean())
            if wet >= WET_SHARE:
                return "wet"
            if wet + inter >= WET_SHARE:
                return "inter"
            if wet + inter >= DAMP_SHARE:
                return "damp"
        if "weather" in summary.columns:
            wx = summary["weather"].to_numpy(dtype=float)
            if np.isfinite(wx).any() and float(np.mean(wx[np.isfinite(wx)] >= RAIN_WEATHER)) >= RAIN_SHARE:
                return "damp"
    tokens = _tokens(source_name or "")
    if "wet" in tokens or "rain" in tokens:
        return "wet"
    if "inter" in tokens or "damp" in tokens:
        return "inter" if "inter" in tokens else "damp"
    return "dry"


def infer_tags(source_name: str | None, summary: pd.DataFrame) -> tuple[str, str]:
    """(session_type, conditions string) — conditions is '' for a dry session."""
    session_type = type_from_name(source_name) or type_from_laps(summary)
    state = state_from_telemetry(summary, source_name)
    conditions = compose_conditions(state, "auto: tyres / weather") if state != "dry" else ""
    return session_type, conditions


def backfill_session_tags(app_root: Path | None = None) -> int:
    """
    Fill an empty session type / track state from the file name and telemetry.
    Never overwrites a tag the user set. Returns the number of sessions changed.
    """
    from .tyres import session_summary

    sessions = list_sessions(app_root)
    changed = 0
    for _, row in sessions.iterrows():
        cur_type = str(row.get("session_type") or "").strip()
        cur_cond = str(row.get("conditions") or "").strip()
        if cur_type and cur_cond:
            continue
        sid = int(row["id"])
        try:
            session, summary = session_summary(sid, app_root)
        except Exception:  # a missing / unreadable telemetry file must not block startup
            continue
        if session is None:
            continue
        new_type, new_cond = infer_tags(session.get("source_name"), summary)
        updates = {}
        if not cur_type and new_type:
            updates["session_type"] = new_type
        if not cur_cond and new_cond:
            updates["conditions"] = new_cond
        if updates:
            sets = ", ".join(f"{k} = ?" for k in updates)
            with connect(app_root) as conn:
                conn.execute(f"UPDATE sessions SET {sets} WHERE id = ?", (*updates.values(), sid))
            changed += 1
    return changed

