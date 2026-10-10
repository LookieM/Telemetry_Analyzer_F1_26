"""WebSocket /ws/live and a REST status for the live view."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from ..serialization import to_jsonable

router = APIRouter()
COOKIE = "telemetria_token"


def _ingest(app):
    return getattr(app.state, "ingest", None)


@router.get("/api/live/status")
def live_status(request: Request):
    ing = _ingest(request.app)
    if ing is None:
        return {"enabled": False}
    return to_jsonable({"enabled": True, **ing.status(), "snapshot": ing.engine.snapshot()})


@router.websocket("/ws/live")
async def live_ws(ws: WebSocket) -> None:
    token = ws.app.state.config.access_token
    if token and ws.query_params.get("token") != token and ws.cookies.get(COOKIE) != token:
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
