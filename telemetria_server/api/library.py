"""Library endpoints: stats, session list / detail / tags / delete."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from telemetry import db
from telemetry.compounds import get_allocation
from telemetry.conditions import compose_conditions, split_conditions, weather_banner
from telemetry.corners import normalize_track_name

from ..serialization import to_jsonable

router = APIRouter()


class SessionPatch(BaseModel):
    session_type: str | None = None
    conditions: str | None = None  # raw text; or the structured pair below (wins when track_state is set)
    track_state: str | None = None  # dry / damp / inter / wet
    condition_notes: str | None = None
    notes: str | None = None


def _track_state(session: dict[str, Any]) -> dict[str, Any]:
    state, notes = split_conditions(session.get("conditions") or "")
    return {"state": state, "notes": notes, "banner": weather_banner(state)}


def _root(request: Request) -> Path:
    return request.app.state.config.app_root


def _meta(session: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in session.items() if k != "setup_json"}


@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok"}


@router.get("/library/stats")
def library_stats(request: Request) -> Any:
    return to_jsonable(db.library_stats(_root(request)))


@router.get("/sessions")
def list_sessions(request: Request, track: str | None = None, type: str | None = None) -> Any:
    df = db.list_sessions(_root(request), session_type=type or None)
    if df.empty:
        return []
    if track:
        want = normalize_track_name(track) or track
        df = df[df["track"].map(lambda t: (normalize_track_name(t) or t) == want)]
    return to_jsonable(df.drop(columns=["setup_json"], errors="ignore"))


@router.get("/sessions/{session_id}")
def get_session(session_id: int, request: Request) -> Any:
    from telemetry import tyres

    root = _root(request)
    session, summary = tyres.session_summary(session_id, root)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    session = db.get_session(session_id, root) or session  # tags / notes fresh (the summary cache keeps the old row)
    alloc = get_allocation(session.get("track"), root)
    laps = summary.copy()
    if "compound" in laps.columns:
        laps["compound_label"] = [alloc.label(None if pd.isna(c) else int(c)) for c in laps["compound"]]
    return to_jsonable({"session": _meta(session), "laps": laps, "track_state": _track_state(session)})


@router.patch("/sessions/{session_id}")
def patch_session(session_id: int, body: SessionPatch, request: Request) -> Any:
    root = _root(request)
    if not db.get_session(session_id, root):
        raise HTTPException(404, f"Session {session_id} not found")
    conditions = body.conditions
    if body.track_state is not None:
        conditions = compose_conditions(body.track_state, body.condition_notes or "")
    db.update_session_tags(
        session_id,
        session_type=body.session_type,
        conditions=conditions,
        notes=body.notes,
        app_root=root,
    )
    return to_jsonable(_meta(db.get_session(session_id, root)))


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, request: Request) -> dict[str, Any]:
    from telemetry import setup_eval, tyres

    root = _root(request)
    if not db.get_session(session_id, root):
        raise HTTPException(404, f"Session {session_id} not found")
    db.delete_session(session_id, root)
    tyres.clear_cache()
    setup_eval.clear_run_cache()
    return {"deleted": session_id}
