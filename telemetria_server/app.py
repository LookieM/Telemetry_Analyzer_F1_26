"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from telemetry.db import ensure_session_meta_schema, init_db
from telemetry.progress import ensure_progress_schema

from .api import imports, laps, library, settings, strategy, tyres
from .config import REPO_ROOT, Config

COOKIE = "telemetria_token"


def create_app(config: Config | None = None, *, frontend_dist: Path | None = None) -> FastAPI:
    cfg = config or Config()
    dist = frontend_dist if frontend_dist is not None else REPO_ROOT / "frontend" / "dist"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(cfg.app_root)
        ensure_session_meta_schema(cfg.app_root)
        ensure_progress_schema(cfg.app_root)
        yield

    app = FastAPI(title="Telemetria", lifespan=lifespan)
    app.state.config = cfg

    if cfg.access_token:

        @app.middleware("http")
        async def token_gate(request: Request, call_next):
            path = request.url.path
            if not (path.startswith("/api") or path.startswith("/ws")):
                return await call_next(request)
            ok_query = request.query_params.get("token") == cfg.access_token
            if not ok_query and request.cookies.get(COOKIE) != cfg.access_token:
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
            response = await call_next(request)
            if ok_query:
                response.set_cookie(COOKIE, cfg.access_token, httponly=True, samesite="lax")
            return response

    for module in (library, laps, tyres, strategy, settings, imports):
        app.include_router(module.router, prefix="/api")

    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app
