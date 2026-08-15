"""Setup fingerprint timeline linked to session pace."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .corners import normalize_track_name
from .db import (
    connect,
    ensure_session_meta_schema,
    get_session,
    list_sessions,
    update_session_setup_fingerprint,
)

# Human-readable labels for setup keys (subset used in fingerprints / deltas)
_SETUP_LABELS = {
    "fuel_setup": "Fuel",
    "wing_setup_0": "Front wing",
    "wing_setup_1": "Rear wing",
    "diff_onThrottle_setup": "Diff on-throttle",
    "diff_offThrottle_setup": "Diff off-throttle",
    "camber_setup_0": "Camber F",
    "camber_setup_1": "Camber R",
    "toe_setup_0": "Toe F",
    "toe_setup_1": "Toe R",
    "susp_spring_setup_0": "Spring F",
    "susp_spring_setup_1": "Spring R",
    "arb_setup_0": "ARB F",
    "arb_setup_1": "ARB R",
    "susp_height_setup_0": "Ride FL",
    "susp_height_setup_1": "Ride FR",
    "susp_height_setup_2": "Ride RL",
    "susp_height_setup_3": "Ride RR",
    "brake_bias_setup": "Brake bias",
    "brake_press_setup": "Brake press",
    "front_brake_bias": "Front brake bias",
    "tyre_press_setup_0": "Press FL",
    "tyre_press_setup_1": "Press FR",
    "tyre_press_setup_2": "Press RL",
    "tyre_press_setup_3": "Press RR",
    "tyre_compound": "Compound",
}


def _quantize(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 4)
    return value


def normalize_setup_dict(setup: dict[str, Any] | None) -> dict[str, Any]:
    if not setup:
        return {}
    out: dict[str, Any] = {}
    for key in sorted(setup.keys()):
        if key.startswith("_"):
            continue
        val = setup[key]
        if val is None:
            continue
        out[key] = _quantize(val)
    return out


def compute_setup_fingerprint(setup: dict[str, Any] | None) -> str | None:
    """Stable short hash of the meaningful setup channels."""
    norm = normalize_setup_dict(setup)
    if not norm:
        return None
    payload = json.dumps(norm, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def parse_setup_json(raw: str | dict | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def diff_setups(
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """List field-level changes between two setups (current − previous)."""
    a = normalize_setup_dict(previous)
    b = normalize_setup_dict(current)
    keys = sorted(set(a) | set(b))
    rows: list[dict[str, Any]] = []
    for key in keys:
        va, vb = a.get(key), b.get(key)
        if va == vb:
            continue
        delta = None
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            delta = float(vb) - float(va)
        rows.append(
            {
                "key": key,
                "label": _SETUP_LABELS.get(key, key),
                "from": va,
                "to": vb,
                "delta": delta,
            }
        )
    return rows


def format_setup_delta(diffs: list[dict[str, Any]], max_items: int = 6) -> str:
    if not diffs:
        return "unchanged"
    parts: list[str] = []
    for d in diffs[:max_items]:
        if d.get("delta") is not None and isinstance(d["from"], (int, float)):
            parts.append(f"{d['label']} {d['delta']:+.3g}")
        else:
            parts.append(f"{d['label']}: {d['from']}→{d['to']}")
    extra = len(diffs) - max_items
    if extra > 0:
        parts.append(f"+{extra} more")
    return ", ".join(parts)


def fingerprint_for_session(session: dict[str, Any] | None) -> str | None:
    if not session:
        return None
    existing = session.get("setup_fingerprint")
    if existing:
        return str(existing)
    return compute_setup_fingerprint(parse_setup_json(session.get("setup_json")))


def setup_timeline(
    track: str,
    app_root: Path | None = None,
    session_type: str | None = None,
) -> pd.DataFrame:
    """
    Chronological setup evolution for a track.

    Each row links a session's setup fingerprint to that session's best lap,
    plus Δsetup vs the previous visit and pace response (best_lap_time − prev).
    """
    ensure_session_meta_schema(app_root)
    track = normalize_track_name(track) or track
    sessions = list_sessions(app_root, track=track, session_type=session_type)
    if sessions.empty:
        return pd.DataFrame()

    # Oldest → newest for Δ chain
    sessions = sessions.sort_values("created_at", ascending=True).reset_index(drop=True)
    rows: list[dict[str, Any]] = []
    prev_setup: dict[str, Any] | None = None
    prev_time: float | None = None
    prev_fp: str | None = None

    for _, s in sessions.iterrows():
        setup = parse_setup_json(s.get("setup_json"))
        fp = s.get("setup_fingerprint") or compute_setup_fingerprint(setup)
        best = float(s["best_lap_time"]) if pd.notna(s.get("best_lap_time")) else None
        diffs = diff_setups(prev_setup, setup) if prev_setup is not None else []
        pace_delta = (best - prev_time) if (best is not None and prev_time is not None) else None
        rows.append(
            {
                "session_id": int(s["id"]),
                "created_at": s.get("created_at"),
                "car": s.get("car"),
                "session_type": s.get("session_type") or "",
                "conditions": s.get("conditions") or "",
                "best_lap": int(s["best_lap"]) if pd.notna(s.get("best_lap")) else None,
                "best_lap_time": best,
                "setup_fingerprint": fp,
                "setup_changed": bool(diffs) if prev_setup is not None else None,
                "setup_delta_summary": format_setup_delta(diffs) if prev_setup is not None else "— (first)",
                "n_setup_changes": len(diffs) if prev_setup is not None else 0,
                "pace_delta_s": pace_delta,
                "same_fingerprint": (fp == prev_fp) if prev_fp else None,
                "source_name": s.get("source_name"),
                "notes": s.get("notes") or "",
            }
        )
        prev_setup = setup
        prev_time = best
        prev_fp = fp

    return pd.DataFrame(rows)


def setup_delta_between_sessions(
    session_a_id: int,
    session_b_id: int,
    app_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Field deltas from session A → session B."""
    a = get_session(session_a_id, app_root) or {}
    b = get_session(session_b_id, app_root) or {}
    return diff_setups(parse_setup_json(a.get("setup_json")), parse_setup_json(b.get("setup_json")))


def backfill_setup_fingerprints(app_root: Path | None = None) -> int:
    """Fill setup_fingerprint for sessions that only have setup_json."""
    ensure_session_meta_schema(app_root)
    updated = 0
    with connect(app_root) as conn:
        rows = conn.execute(
            """
            SELECT id, setup_json, setup_fingerprint FROM sessions
            WHERE setup_json IS NOT NULL AND setup_json != ''
              AND (setup_fingerprint IS NULL OR setup_fingerprint = '')
            """
        ).fetchall()
    for row in rows:
        fp = compute_setup_fingerprint(parse_setup_json(row["setup_json"]))
        if fp:
            update_session_setup_fingerprint(int(row["id"]), fp, app_root)
            updated += 1
    return updated
