"""Server fixtures: a temporary library copied from the personal one (never the real `data/`)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from telemetria_server.app import create_app
from telemetria_server.config import Config
from conftest import DB_PATH, ROOT, copy_library_db, session_by_source


@pytest.fixture
def lib_root(tmp_path: Path) -> Path:
    """tmp app root holding a copy of the library DB and the Bahrain race parquet."""
    if not DB_PATH.exists():
        pytest.skip("personal telemetry library (data/) not present")
    session = session_by_source("bahrain_race.csv")
    (tmp_path / "data" / "sessions").mkdir(parents=True)
    copy_library_db(tmp_path / "data" / "telemetry.db")
    src = ROOT / session["telemetry_path"]
    shutil.copy2(src, tmp_path / "data" / "sessions" / src.name)
    return tmp_path


@pytest.fixture
def race_id(lib_root: Path) -> int:
    from telemetry.db import list_sessions

    df = list_sessions(lib_root)
    return int(df.loc[df["source_name"] == "bahrain_race.csv", "id"].iloc[0])


@pytest.fixture
def client(lib_root: Path):
    with TestClient(create_app(Config(record=False, app_root=lib_root), frontend_dist=lib_root / "no_dist")) as c:
        yield c


@pytest.fixture
def empty_client(tmp_path: Path):
    with TestClient(create_app(Config(record=False, app_root=tmp_path), frontend_dist=tmp_path / "no_dist")) as c:
        yield c
