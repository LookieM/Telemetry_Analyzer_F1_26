"""WebSocket /ws/live and a REST status for the live view."""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.requests import HTTPConnection
from pydantic import BaseModel, ConfigDict, Field

from ..live.engineer import EngineerError
from ..serialization import to_jsonable

router = APIRouter()
COOKIE = "telemetria_token"


def _ingest(app):
    return getattr(app.state, "ingest", None)


def token_ok(conn: HTTPConnection) -> bool:
    """The live socket's access rule: no token configured, or the token in the query or the cookie."""
    token = conn.app.state.config.access_token
    return not token or conn.query_params.get("token") == token or conn.cookies.get(COOKIE) == token


def live_ingest(conn: HTTPConnection):
    """Dependency for the engineer commands: access token checked, 503 while live ingest is disabled."""
    if not token_ok(conn):
        raise HTTPException(401, "Unauthorized")
    ing = _ingest(conn.app)
    if ing is None:
        raise HTTPException(503, "Live ingest is disabled")
    return ing


class StartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program: Literal["short", "full"]
    minutes: float | None = Field(default=None, gt=0, le=180)


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["1", "2", "same"]
    strength: Literal["slight", "clear"] = "slight"
    tags: list[str] = []
    note: str | None = Field(default=None, max_length=500)


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    winner: Literal["1", "2"]


class RevertIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accept: bool


class DuelStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: Literal[2, 3]
    names: list[str] = Field(default=[], max_length=3)


class DuelRankIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: list[str] = Field(min_length=2, max_length=3)
    note: str | None = Field(default=None, max_length=500)


class DuelConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    winner: str = Field(min_length=1, max_length=1)


def _command(fn, *args, **kwargs) -> dict:
    try:
        return to_jsonable(fn(*args, **kwargs))
    except EngineerError as exc:
        raise HTTPException(409, exc.reason) from exc


@router.post("/api/live/engineer/start")
def engineer_start(body: StartIn, ing=Depends(live_ingest)):
    return _command(ing.engine.engineer_start, body.program, body.minutes)


@router.post("/api/live/engineer/answer")
def engineer_answer(body: AnswerIn, ing=Depends(live_ingest)):
    return _command(ing.engine.engineer_command, "answer", body.verdict, body.strength, body.tags, body.note)


@router.post("/api/live/engineer/confirm")
def engineer_confirm(body: ConfirmIn, ing=Depends(live_ingest)):
    return _command(ing.engine.engineer_command, "confirm", body.winner)


@router.post("/api/live/engineer/revert")
def engineer_revert(body: RevertIn, ing=Depends(live_ingest)):
    return _command(ing.engine.engineer_command, "revert", body.accept)


@router.post("/api/live/engineer/skip")
def engineer_skip(ing=Depends(live_ingest)):
    return _command(ing.engine.engineer_command, "skip")


@router.post("/api/live/engineer/next-phase")
def engineer_next_phase(ing=Depends(live_ingest)):
    return _command(ing.engine.engineer_command, "next_phase")


@router.post("/api/live/engineer/stop")
def engineer_stop(ing=Depends(live_ingest)):
    return _command(ing.engine.engineer_command, "stop")


@router.post("/api/live/duel/start")
def duel_start(body: DuelStartIn, ing=Depends(live_ingest)):
    return _command(ing.engine.duel_start, body.n, body.names)


@router.post("/api/live/duel/rank")
def duel_rank(body: DuelRankIn, ing=Depends(live_ingest)):
    return _command(ing.engine.duel_command, "rank", body.order, body.note)


@router.post("/api/live/duel/confirm")
def duel_confirm(body: DuelConfirmIn, ing=Depends(live_ingest)):
    return _command(ing.engine.duel_command, "confirm", body.winner)


@router.post("/api/live/duel/skip")
def duel_skip(ing=Depends(live_ingest)):
    return _command(ing.engine.duel_command, "skip_contestant")


@router.post("/api/live/duel/stop")
def duel_stop(ing=Depends(live_ingest)):
    return _command(ing.engine.duel_command, "stop")


@router.get("/api/live/status")
def live_status(request: Request):
    ing = _ingest(request.app)
    if ing is None:
        return {"enabled": False}
    return to_jsonable({"enabled": True, **ing.status(), "snapshot": ing.engine.snapshot()})


@router.websocket("/ws/live")
async def live_ws(ws: WebSocket) -> None:
    if not token_ok(ws):
        await ws.close(code=4401)
        return
    ing = _ingest(ws.app)
    await ws.accept()
    if ing is None:
        await ws.send_json({"type": "status", "connected": False, "enabled": False})
        await ws.close()
        return
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    ing.clients.add(q)
    try:
        await ws.send_json(ing.status())
        for ev in list(ing.recent_events):
            await ws.send_json(to_jsonable(ev))
        while True:
            await ws.send_json(await q.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        ing.clients.discard(q)
