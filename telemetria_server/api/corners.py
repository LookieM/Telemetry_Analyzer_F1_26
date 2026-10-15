"""Corners: the per-track corner set and the per-corner comparison of a lap against a reference."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from telemetry import corner_store
from telemetry.corner_balance import BALANCE_COLUMNS, NEUTRAL_DEG, balance_summary, lap_balance, session_balance
from telemetry.corner_report import REPORT_COLUMNS, corner_report
from telemetry.corners import normalize_track_name
from telemetry.db import get_session_laps
from telemetry.metrics import get_lap

from ..serialization import to_jsonable
from ._common import lap_or_404, load_columns, root_of, session_or_404

router = APIRouter()

FRAME_COLUMNS = [*dict.fromkeys([*REPORT_COLUMNS, "lap", "bin_index", *BALANCE_COLUMNS])]


class RebuildBody(BaseModel):
    session: int
    lap: int


def _best_lap(session_id: int, root: Path) -> int:
    laps = get_session_laps(session_id, root)
    if laps.empty:
        raise HTTPException(404, f"Session {session_id} has no laps")
    flagged = laps[laps["is_best"] == 1]
    return int((flagged if not flagged.empty else laps.sort_values("lap_time")).iloc[0]["lap"])


def _session_track(session: dict[str, Any]) -> str:
    track = normalize_track_name(session.get("track"))
    if not track:
        raise HTTPException(422, f"Session {session['id']} has no track")
    return track


def _stored(track: str, root: Path) -> dict[str, Any]:
    try:
        return corner_store.ensure_track_corners(track, root)
    except corner_store.NoCleanLap as exc:
        raise HTTPException(404, str(exc)) from exc


def _balance_block(balance: dict[str, Any], corners: list[dict[str, Any]]) -> dict[str, Any]:
    """The part of a balance result that is shared by /corners and /balance."""
    ok = balance["available"]
    return {
        "balance_available": ok,
        "balance_reason": balance["reason"],
        "balance_baseline": NEUTRAL_DEG,
        "balance_summary": balance_summary(balance["corners"], corners) if ok else None,
        "lockups": balance["lockups"],
    }


@router.get("/sessions/{session_id}/corners")
def session_corners(session_id: int, request: Request, lap: int | None = None, ref_lap: int | None = None, ref_session: int | None = None) -> Any:
    root = root_of(request)
    session = session_or_404(session_id, root)
    track = _session_track(session)
    ref_id = ref_session if ref_session is not None else session_id
    if ref_id != session_id:
        ref_meta = session_or_404(ref_id, root)
        if normalize_track_name(ref_meta.get("track")) != track:
            raise HTTPException(422, f"Reference session {ref_id} is not on {track}")
    lap = lap if lap is not None else _best_lap(session_id, root)
    ref_lap = ref_lap if ref_lap is not None else _best_lap(ref_id, root)

    df = load_columns(session_id, root, FRAME_COLUMNS)
    focus = lap_or_404(df, lap, session_id)
    ref_df = lap_or_404(df if ref_id == session_id else load_columns(ref_id, root, FRAME_COLUMNS), ref_lap, ref_id)
    stored = _stored(track, root)
    try:
        report = corner_report(focus, ref_df, stored["corners"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    balance = lap_balance(focus, stored["corners"])
    if balance["available"]:
        for row, b in zip(report["corners"], balance["corners"]):
            row["balance"] = {k: b[k] for k in ("entry", "mid", "exit", "traction", "lockups")}
    else:
        for row in report["corners"]:
            row["balance"] = None
    return to_jsonable(
        {
            "track": track,
            "session_id": session_id,
            "lap": lap,
            "reference": {"session": ref_id, "lap": ref_lap},
            "corners_source": {"session": stored["source_session"], "lap": stored["source_lap"], "built_at": stored["built_at"]},
            **report,
            **_balance_block(balance, stored["corners"]),
        }
    )


@router.get("/sessions/{session_id}/balance")
def session_balance_view(session_id: int, request: Request) -> Any:
    """Balance per corner and phase as the median over the session's clean laps."""
    root = root_of(request)
    session = session_or_404(session_id, root)
    track = _session_track(session)
    stored = _stored(track, root)
    corners = stored["corners"]
    df = load_columns(session_id, root, [*corner_store.FRAME_COLUMNS, *BALANCE_COLUMNS])
    laps = corner_store.clean_laps(df) if "lap_distance" in df.columns else None
    lap_numbers = [int(x) for x in laps["lap"]] if laps is not None and not laps.empty else []
    per_lap = []
    for n in lap_numbers:
        b = lap_balance(get_lap(df, n), corners)
        per_lap.append({**b, "lap": n})
        if not b["available"]:
            break  # a missing channel is missing on every lap
    if per_lap:
        result = session_balance(per_lap, corners)
    else:
        result = {"available": False, "reason": "No clean laps in this session to measure balance on", "corners": [], "lockups": [], "laps": 0}
    rows = [
        {"id": c["id"], "name": c["name"], "speed_class": c["speed_class"], **{k: b[k] for k in ("entry", "mid", "exit", "traction", "lockups")}}
        for c, b in zip(corners, result["corners"])
    ]
    return to_jsonable(
        {
            "track": track,
            "session_id": session_id,
            "laps": result["laps"],
            "lap_numbers": lap_numbers if result["available"] else [],
            "corners": rows,
            **_balance_block(result, corners),
        }
    )


@router.get("/tracks/{track}/corners")
def track_corners(track: str, request: Request) -> Any:
    root = root_of(request)
    name = normalize_track_name(track) or track
    stored = _stored(name, root)
    return to_jsonable(stored)


@router.post("/tracks/{track}/corners/rebuild")
def rebuild_corners(track: str, body: RebuildBody, request: Request) -> Any:
    root = root_of(request)
    name = normalize_track_name(track) or track
    session = session_or_404(body.session, root)
    if normalize_track_name(session.get("track")) != name:
        raise HTTPException(422, f"Session {body.session} is not on {name}")
    frame = lap_or_404(load_columns(body.session, root, FRAME_COLUMNS), body.lap, body.session)
    if frame.empty:
        raise HTTPException(404, f"Lap {body.lap} not found in session {body.session}")
    try:
        return to_jsonable(corner_store.build_track_corners(name, body.session, body.lap, root))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
