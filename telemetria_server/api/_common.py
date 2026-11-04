"""Helpers shared by the API routers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException, Request

from telemetry import db


def root_of(request: Request) -> Path:
    return request.app.state.config.app_root


def session_or_404(session_id: int, root: Path) -> dict[str, Any]:
    session = db.get_session(session_id, root)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    return session


def load_columns(session_id: int, root: Path, columns: list[str] | None) -> pd.DataFrame:
    """Selected parquet columns of a stored session, None = all (404 when the file is gone)."""
    try:
        return db.load_session_telemetry(session_id, root, columns=columns)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


def lap_or_404(df: pd.DataFrame, lap: int, session_id: int) -> pd.DataFrame:
    from telemetry.metrics import get_lap

    out = get_lap(df, lap)
    if out.empty:
        raise HTTPException(404, f"Lap {lap} not found in session {session_id}")
    return out
