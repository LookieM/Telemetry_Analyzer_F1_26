"""Shared fixtures. Tests that need the personal telemetry library skip when `data/` is absent."""

from __future__ import annotations

import sqlite3
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore")

DB_PATH = ROOT / "data" / "telemetry.db"
needs_library = pytest.mark.skipif(not DB_PATH.exists(), reason="personal telemetry library (data/) not present")


def session_by_source(name: str) -> dict:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT * FROM sessions WHERE source_name = ?", (name,)).fetchone()
    finally:
        con.close()
    if row is None:
        pytest.skip(f"{name} not imported in this library")
    return dict(row)


def session_df(session: dict) -> pd.DataFrame:
    return pd.read_parquet(ROOT / session["telemetry_path"])


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    """Empty app root with an initialised DB + journal schema."""
    from telemetry.db import init_db
    from telemetry.setup_log import ensure_log_schema

    init_db(tmp_path)
    ensure_log_schema(tmp_path)
    return tmp_path
