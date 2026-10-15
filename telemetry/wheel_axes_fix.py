"""One-off library upkeep: correct the wheel order and g-force axes stored in earlier imports."""

from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .db import connect, db_path, default_data_dir, ensure_session_meta_schema

FLAG = "wheel_axes_fix_v1"


def _backup_db(app_root: Path | None, label: str) -> Path:
    """Consistent copy of the library database into data/backups/<timestamp>-<label>/."""
    dest = default_data_dir(app_root) / "backups" / f"{datetime.now():%Y%m%d-%H%M%S}-{label}"
    dest.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(db_path(app_root)))
    dst = sqlite3.connect(str(dest / "telemetry.db"))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return dest


def _set(df: pd.DataFrame, col: str, values: Any) -> None:
    """Assign keeping the stored dtype (compact parquets hold float32)."""
    dtype = df[col].dtype if col in df.columns else np.float32
    df[col] = np.asarray(values, dtype=float).astype(dtype)


def repaired_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Stored g and lock-up columns corrected. Earlier loaders read g_lat from gforce_X (really minus
    longitudinal) and g_long from gforce_Z (vertical), and split lock-ups with the wheels back to front.
    Raw per-wheel arrays are not touched.
    """
    df = df.copy()
    if "gforce_X" in df.columns and "gforce_Y" in df.columns:
        lat = df["gforce_Y"].to_numpy(float)
        lon = -df["gforce_X"].to_numpy(float)
        _set(df, "g_lat", lat)
        _set(df, "g_long", lon)
        _set(df, "g_mag", np.sqrt(lat**2 + lon**2))
    elif "g_lat" in df.columns:
        # Compact import: the stored g_lat is minus longitudinal, g_long is vertical, lateral was never kept.
        lon = -df["g_lat"].to_numpy(float)
        _set(df, "g_long", lon)
        _set(df, "g_lat", np.full(len(df), np.nan))
        if "g_mag" in df.columns:
            _set(df, "g_mag", np.full(len(df), np.nan))
    if "lockup_front" in df.columns and "lockup_rear" in df.columns:
        df["lockup_front"], df["lockup_rear"] = df["lockup_rear"].copy(), df["lockup_front"].copy()
    return df


def _rewrite_parquet(path: Path) -> None:
    """Atomic rewrite: temp file next to the original, then os.replace."""
    out = repaired_frame(pd.read_parquet(path))
    tmp = path.with_name(path.name + ".tmp")
    try:
        out.to_parquet(tmp, compression="zstd", index=False)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def repair_library_wheel_axes(app_root: Path | None = None) -> dict[str, Any]:
    """
    Fix every stored session for the front-first wheel order and the SRT g-force axes. The database and
    every parquet that gets rewritten are backed up first. Compact imports (no raw gforce_*) get
    g_long = -old g_lat and report lateral g as missing. The laps table needs no change (lockup_samples
    counts front + rear). Runs once: completion is recorded in `library_meta`; each rewritten session is
    recorded too, so an interrupted run never swaps a file twice.

    Returns ``{"done", "repaired", "skipped", "backup"}``; ``done`` is False when already fixed.
    """
    ensure_session_meta_schema(app_root)
    with connect(app_root) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS library_meta (key TEXT PRIMARY KEY, value TEXT)")
        if conn.execute("SELECT 1 FROM library_meta WHERE key = ?", (FLAG,)).fetchone():
            return {"done": False, "repaired": 0, "skipped": 0, "backup": None}
        rows = conn.execute("SELECT id, telemetry_path FROM sessions").fetchall()
        finished = {r[0] for r in conn.execute("SELECT key FROM library_meta WHERE key LIKE ?", (f"{FLAG}:%",))}
    root = app_root or Path(__file__).resolve().parent.parent
    todo = [(int(r["id"]), root / r["telemetry_path"], r["telemetry_path"]) for r in rows if f"{FLAG}:{int(r['id'])}" not in finished]
    todo = [t for t in todo if t[1].exists()]
    skipped = len(rows) - len(todo)
    backup = _backup_db(app_root, "before-wheel-axes-fix") if rows else None
    if backup:
        for _, path, rel in todo:
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    repaired = 0
    for sid, path, _ in todo:
        try:
            _rewrite_parquet(path)
        except (OSError, ValueError):
            skipped += 1
            continue
        repaired += 1
        with connect(app_root) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO library_meta (key, value) VALUES (?, ?)",
                (f"{FLAG}:{sid}", datetime.now().isoformat(timespec="seconds")),
            )
    with connect(app_root) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO library_meta (key, value) VALUES (?, ?)",
            (FLAG, datetime.now().isoformat(timespec="seconds")),
        )
    return {"done": True, "repaired": repaired, "skipped": skipped, "backup": str(backup) if backup else None}
