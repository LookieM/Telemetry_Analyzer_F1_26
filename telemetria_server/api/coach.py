"""Coach: the session read (diagnosis headline) and the ranked engineer callouts over the whole session."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request

from telemetry.coach import CoachItem, coach_feed_for_session, setup_followup_items
from telemetry.setup_log import followup_entries

from ..serialization import to_jsonable
from ._common import load_columns, root_of, session_or_404

router = APIRouter()


def _item(item: CoachItem) -> dict[str, Any]:
    out = asdict(item)
    out["score"] = item.score
    return out


@router.get("/sessions/{session_id}/coach")
def session_coach(session_id: int, request: Request) -> Any:
    root = root_of(request)
    session = session_or_404(session_id, root)
    df = load_columns(session_id, root, None)  # the callouts read many channels: load them all
    followups = setup_followup_items(followup_entries(session_id, root))
    diag, top, rest = coach_feed_for_session(
        df,
        track=session.get("track"),
        track_length=session.get("track_length"),
        conditions=session.get("conditions"),
        extra_items=followups or None,
    )
    return to_jsonable(
        {
            "session_id": session_id,
            "headline": diag.headline,
            "diagnosis": {
                "focus_lap": diag.focus_lap,
                "ref_lap": diag.ref_lap,
                "primary_issue": diag.primary_issue,
                "phase": diag.phase,
                "strength": diag.strength,
                "worst_corner": diag.worst_corner,
                "worst_corner_loss_s": diag.worst_corner_loss_s,
                "confidence": diag.confidence,
                "track_state": diag.track_state,
            },
            "top": [_item(i) for i in top],
            "rest": [_item(i) for i in rest],
        }
    )
