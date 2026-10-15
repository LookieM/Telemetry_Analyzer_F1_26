"""SQLite session library + compact Parquet telemetry storage."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

import pandas as pd

from .loader import SETUP_CHANNEL_KEYS

# Core channels every analysis relies on (always kept, fixed dtypes). Any other numeric export
# channel that varies over the session is kept too — suspension, brakes, inner tyre temps, etc.
COMPACT_COLUMNS = [
    "lap",
    "bin_index",
    "lap_distance",
    "lap_time",
    "pos_x",
    "pos_y",
    "pos_z",
    "speed",
    "throttle",
    "brake",
    "gear",
    "steering",
    "rpm",
    "fuel",
    "drs",
    "g_lat",
    "g_long",
    "g_mag",
    "ers_store_mj",
    "ers_deployMode",
    "ers_deployed",
    "ers_harv_mguk",
    "ers_harv_mguh",
    "ice_power",
    "mguk_power",
    "overtake",
    "overtake_allowed",
    "activeAero_mode",
    "slip_max",
    "lockup_risk",
    "lockup_front",
    "lockup_rear",
    "coasting",
    "trail_braking",
    "tyre_compound_0",
    "tyre_temp_0",
    "tyre_temp_1",
    "tyre_temp_2",
    "tyre_temp_3",
    "tyre_wear_0",
    "tyre_wear_1",
    "tyre_wear_2",
    "tyre_wear_3",
    "tyre_press_0",
    "tyre_press_1",
    "tyre_press_2",
    "tyre_press_3",
    *SETUP_CHANNEL_KEYS,
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_hash TEXT NOT NULL UNIQUE,
    track TEXT,
    car TEXT,
    track_length REAL,
    notes TEXT DEFAULT '',
    sample_count INTEGER,
    lap_count INTEGER,
    best_lap INTEGER,
    best_lap_time REAL,
    telemetry_path TEXT NOT NULL,
    setup_json TEXT,
    original_size_bytes INTEGER,
    stored_size_bytes INTEGER,
    source_deleted INTEGER DEFAULT 0,
    session_type TEXT DEFAULT '',
    conditions TEXT DEFAULT '',
    setup_fingerprint TEXT
);

CREATE TABLE IF NOT EXISTS laps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    lap INTEGER NOT NULL,
    lap_time REAL NOT NULL,
    delta_best REAL,
    vmax REAL,
    vavg REAL,
    throttle_full_pct REAL,
    coast_pct REAL,
    brake_pct REAL,
    fuel_start REAL,
    fuel_end REAL,
    fuel_used REAL,
    tyre_wear_avg REAL,
    tyre_temp_avg REAL,
    compound INTEGER,
    ers_start_mj REAL,
    ers_end_mj REAL,
    lockup_samples INTEGER,
    is_best INTEGER DEFAULT 0,
    insights_json TEXT,
    UNIQUE(session_id, lap)
);

CREATE TABLE IF NOT EXISTS track_maps (
    track TEXT PRIMARY KEY,
    outline_json TEXT NOT NULL,
    sample_count INTEGER,
    updated_at TEXT NOT NULL,
    source_session_id INTEGER
);

CREATE TABLE IF NOT EXISTS track_corners (
    track TEXT PRIMARY KEY,
    corners_json TEXT NOT NULL,
    source_session_id INTEGER,
    source_lap INTEGER,
    built_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_laps_session ON laps(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_track ON sessions(track);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at DESC);
"""

# Session type tags for dossier filters / race-ops notebook
SESSION_TYPES = ("FP1", "FP2", "FP3", "Quali", "Race", "Test")

# Columns added after the initial SCHEMA (ALTER / ensure_* — never break old DBs)
_SESSION_META_COLUMNS: dict[str, str] = {
    "session_type": "TEXT DEFAULT ''",
    "conditions": "TEXT DEFAULT ''",
    "setup_fingerprint": "TEXT",
}


def default_data_dir(app_root: Path | None = None) -> Path:
    root = app_root or Path(__file__).resolve().parent.parent
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "sessions").mkdir(parents=True, exist_ok=True)
    return data


def db_path(app_root: Path | None = None) -> Path:
    return default_data_dir(app_root) / "telemetry.db"


def file_hash(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] if isinstance(r, sqlite3.Row) else r[1] for r in rows}


def ensure_session_meta_schema(app_root: Path | None = None) -> None:
    """Add session_type / conditions / setup_fingerprint without rewriting old DBs."""
    with connect(app_root) as conn:
        existing = _table_columns(conn, "sessions")
        for col, decl in _SESSION_META_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {decl}")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_type ON sessions(session_type)"
        )


_SCHEMA_READY: set[str] = set()  # DB paths whose base schema was already created in this process


@contextmanager
def connect(app_root: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = db_path(app_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        key = str(path.resolve())
        if key not in _SCHEMA_READY:
            conn.execute("PRAGMA journal_mode = WAL")  # persistent; lets readers and the recorder coexist
            conn.executescript(SCHEMA)
            _SCHEMA_READY.add(key)
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(app_root: Path | None = None) -> Path:
    with connect(app_root) as conn:
        conn.execute("SELECT 1")
    ensure_session_meta_schema(app_root)
    return db_path(app_root)


def _extra_channels(df: pd.DataFrame, core: list[str]) -> list[str]:
    """
    Every other numeric export channel. Constant ones are kept too: a session-long value
    (weather, track temperature, a pit timer that stayed at 0) is information, and Parquet
    stores a constant column in a few bytes.
    """
    return [
        c
        for c in df.columns
        if c not in core and (pd.api.types.is_numeric_dtype(df[c]) or pd.api.types.is_bool_dtype(df[c]))
    ]


def compact_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in COMPACT_COLUMNS if c in df.columns]
    extra = _extra_channels(df, cols)
    out = df[cols + extra].copy()
    # Downcast floats to save disk
    for c in out.select_dtypes(include=["float64"]).columns:
        out[c] = out[c].astype("float32")
    for c in out.select_dtypes(include=["int64"]).columns:
        if c in ("lap", "bin_index", "gear", "tyre_compound_0", "ers_deployMode", "drs"):
            out[c] = out[c].astype("int16")
        elif c in extra:
            out[c] = pd.to_numeric(out[c], downcast="integer")
    for c in ("lockup_risk", "coasting", "trail_braking"):
        if c in out.columns:
            out[c] = out[c].fillna(False).astype("bool")
    return out


def extract_track_outline(df: pd.DataFrame, max_points: int = 800) -> dict[str, Any]:
    """Build a 2D outline from the fastest valid lap (X/Y plane)."""
    if "pos_x" not in df.columns or "pos_y" not in df.columns:
        return {"x": [], "y": [], "distance": []}

    from .metrics import build_lap_summary, get_lap

    summary = build_lap_summary(df)
    if summary.empty:
        # Fallback: first lap with positions
        lap_df = df.dropna(subset=["pos_x", "pos_y"]).head(5000)
    else:
        best = int(summary.loc[summary["is_best"], "lap"].iloc[0])
        lap_df = get_lap(df, best)

    if lap_df.empty:
        return {"x": [], "y": [], "distance": []}

    step = max(1, len(lap_df) // max_points)
    sample = lap_df.iloc[::step]
    return {
        "x": [float(v) for v in sample["pos_x"]],
        "y": [float(v) for v in sample["pos_y"]],
        "distance": [float(v) for v in sample["lap_distance"]] if "lap_distance" in sample.columns else [],
        "points": int(len(sample)),
    }


def list_sessions(
    app_root: Path | None = None,
    track: str | None = None,
    session_type: str | None = None,
) -> pd.DataFrame:
    ensure_session_meta_schema(app_root)
    clauses: list[str] = []
    params: list[Any] = []
    if track:
        clauses.append("track = ?")
        params.append(track)
    if session_type:
        clauses.append("session_type = ?")
        params.append(session_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(app_root) as conn:
        rows = conn.execute(
            f"SELECT * FROM sessions {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


def get_session(session_id: int, app_root: Path | None = None) -> dict[str, Any] | None:
    with connect(app_root) as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def get_session_laps(session_id: int, app_root: Path | None = None) -> pd.DataFrame:
    with connect(app_root) as conn:
        rows = conn.execute(
            "SELECT * FROM laps WHERE session_id = ? ORDER BY lap",
            (session_id,),
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


# What lap / stint / tyre / journal analysis reads. Background work (library-wide models,
# journal scoring, progress) loads only these instead of all ~290 export channels.
ANALYSIS_COLUMNS: tuple[str, ...] = (
    *COMPACT_COLUMNS,
    "trackLength",
    "tyres_age",
    "pit_status",
    "pitStopTime",
    "pitLaneTime",
    "safetyCarStatus",
    "lap_time_invalid",
    "weather",
    "track_temp",
    "air_temp",
    *(f"tyre_tempInternalAir_{i}" for i in range(4)),
    *(f"brake_temp_{i}" for i in range(4)),
)


def load_session_telemetry(
    session_id: int,
    app_root: Path | None = None,
    *,
    columns: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Stored telemetry; `columns` limits the read to those present (e.g. ANALYSIS_COLUMNS)."""
    session = get_session(session_id, app_root)
    if not session:
        raise FileNotFoundError(f"Session {session_id} not found")
    root = app_root or Path(__file__).resolve().parent.parent
    path = root / session["telemetry_path"]
    if not path.exists():
        raise FileNotFoundError(f"Telemetry file missing: {path}")
    if columns is None:
        return pd.read_parquet(path)
    import pyarrow.parquet as pq

    present = set(pq.read_schema(path).names)
    return pd.read_parquet(path, columns=[c for c in dict.fromkeys(columns) if c in present])


def get_track_outline(track: str, app_root: Path | None = None) -> dict[str, Any] | None:
    with connect(app_root) as conn:
        row = conn.execute(
            "SELECT outline_json FROM track_maps WHERE track = ?",
            (track,),
        ).fetchone()
    if not row:
        return None
    return json.loads(row["outline_json"])


def list_tracks(app_root: Path | None = None) -> list[str]:
    with connect(app_root) as conn:
        rows = conn.execute(
            "SELECT DISTINCT track FROM sessions WHERE track IS NOT NULL ORDER BY track"
        ).fetchall()
    return [r["track"] for r in rows]


def update_session_notes(session_id: int, notes: str, app_root: Path | None = None) -> None:
    with connect(app_root) as conn:
        conn.execute("UPDATE sessions SET notes = ? WHERE id = ?", (notes, session_id))


def update_session_tags(
    session_id: int,
    *,
    session_type: str | None = None,
    conditions: str | None = None,
    notes: str | None = None,
    app_root: Path | None = None,
) -> None:
    """Update session type / conditions / notes (None = leave unchanged)."""
    ensure_session_meta_schema(app_root)
    sets: list[str] = []
    params: list[Any] = []
    if session_type is not None:
        sets.append("session_type = ?")
        params.append(session_type.strip())
    if conditions is not None:
        sets.append("conditions = ?")
        params.append(conditions.strip())
    if notes is not None:
        sets.append("notes = ?")
        params.append(notes)
    if not sets:
        return
    params.append(session_id)
    with connect(app_root) as conn:
        conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?", params)


def update_session_setup_fingerprint(
    session_id: int,
    fingerprint: str | None,
    app_root: Path | None = None,
) -> None:
    ensure_session_meta_schema(app_root)
    with connect(app_root) as conn:
        conn.execute(
            "UPDATE sessions SET setup_fingerprint = ? WHERE id = ?",
            (fingerprint, session_id),
        )


def delete_session(session_id: int, app_root: Path | None = None) -> None:
    root = app_root or Path(__file__).resolve().parent.parent
    session = get_session(session_id, app_root)
    if not session:
        return
    tel = root / session["telemetry_path"]
    with connect(app_root) as conn:
        conn.execute("DELETE FROM laps WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        # Setup journal tables are created lazily (setup_log.py); clean them when present.
        for sql in (
            "DELETE FROM setup_experiments WHERE from_session_id = ? OR to_session_id = ?",
            "DELETE FROM setup_recommendations WHERE session_id = ?",
            # Advice judged against this session goes back to waiting for a follow-up
            # (evaluate_track re-matches it when a later session exists).
            "UPDATE setup_recommendations SET status = 'pending', followup_session_id = NULL, "
            "applied_frac = NULL WHERE followup_session_id = ?",
        ):
            try:
                conn.execute(sql, (session_id,) * sql.count("?"))
            except sqlite3.OperationalError:
                pass
        try:
            conn.execute("DELETE FROM setup_eval_state")
        except sqlite3.OperationalError:
            pass
    if tel.exists():
        tel.unlink()


def find_by_hash(source_hash: str, app_root: Path | None = None) -> dict[str, Any] | None:
    with connect(app_root) as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE source_hash = ?",
            (source_hash,),
        ).fetchone()
    return dict(row) if row else None


def upsert_track_map(
    track: str,
    outline: dict[str, Any],
    session_id: int | None,
    app_root: Path | None = None,
) -> None:
    if not track or not outline.get("x"):
        return
    now = datetime.now(timezone.utc).isoformat()
    with connect(app_root) as conn:
        conn.execute(
            """
            INSERT INTO track_maps (track, outline_json, sample_count, updated_at, source_session_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(track) DO UPDATE SET
                outline_json = excluded.outline_json,
                sample_count = excluded.sample_count,
                updated_at = excluded.updated_at,
                source_session_id = excluded.source_session_id
            """,
            (
                track,
                json.dumps(outline),
                int(outline.get("points") or len(outline.get("x", []))),
                now,
                session_id,
            ),
        )


def insert_imported_session(
    *,
    source_name: str,
    source_hash: str,
    meta: dict[str, Any],
    summary: pd.DataFrame,
    insights_by_lap: dict[int, list[dict]],
    setup: dict[str, Any],
    telemetry_relpath: str,
    original_size: int,
    stored_size: int,
    source_deleted: bool,
    app_root: Path | None = None,
    notes: str = "",
    session_type: str = "",
    conditions: str = "",
    setup_fingerprint: str | None = None,
) -> int:
    ensure_session_meta_schema(app_root)
    now = datetime.now(timezone.utc).isoformat()
    best_lap = int(summary.loc[summary["is_best"], "lap"].iloc[0]) if not summary.empty else None
    best_time = float(summary["lap_time"].min()) if not summary.empty else None

    with connect(app_root) as conn:
        cur = conn.execute(
            """
            INSERT INTO sessions (
                created_at, source_name, source_hash, track, car, track_length, notes,
                sample_count, lap_count, best_lap, best_lap_time, telemetry_path,
                setup_json, original_size_bytes, stored_size_bytes, source_deleted,
                session_type, conditions, setup_fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                source_name,
                source_hash,
                meta.get("track"),
                meta.get("car"),
                meta.get("track_length"),
                notes or "",
                int(meta.get("samples") or 0),
                int(len(summary)),
                best_lap,
                best_time,
                telemetry_relpath,
                json.dumps(setup),
                original_size,
                stored_size,
                1 if source_deleted else 0,
                (session_type or "").strip(),
                (conditions or "").strip(),
                setup_fingerprint,
            ),
        )
        session_id = int(cur.lastrowid)

        for _, row in summary.iterrows():
            lap = int(row["lap"])
            insights = insights_by_lap.get(lap, [])
            conn.execute(
                """
                INSERT INTO laps (
                    session_id, lap, lap_time, delta_best, vmax, vavg, throttle_full_pct,
                    coast_pct, brake_pct, fuel_start, fuel_end, fuel_used, tyre_wear_avg,
                    tyre_temp_avg, compound, ers_start_mj, ers_end_mj, lockup_samples,
                    is_best, insights_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    lap,
                    float(row["lap_time"]),
                    float(row.get("delta_best") or 0),
                    _maybe_float(row, "vmax"),
                    _maybe_float(row, "vavg"),
                    _maybe_float(row, "throttle_full_pct"),
                    _maybe_float(row, "coast_pct"),
                    _maybe_float(row, "brake_pct"),
                    _maybe_float(row, "fuel_start"),
                    _maybe_float(row, "fuel_end"),
                    _maybe_float(row, "fuel_used"),
                    _maybe_float(row, "tyre_wear_avg"),
                    _maybe_float(row, "tyre_temp_avg"),
                    int(row["compound"]) if pd.notna(row.get("compound")) else None,
                    _maybe_float(row, "ers_start_mj"),
                    _maybe_float(row, "ers_end_mj"),
                    int(row["lockup_samples"]) if pd.notna(row.get("lockup_samples")) else 0,
                    1 if bool(row.get("is_best")) else 0,
                    json.dumps(insights),
                ),
            )
    return session_id


def _maybe_float(row: pd.Series, key: str) -> float | None:
    if key not in row or pd.isna(row.get(key)):
        return None
    return float(row[key])


def library_stats(app_root: Path | None = None) -> dict[str, Any]:
    with connect(app_root) as conn:
        sessions = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(stored_size_bytes),0) AS stored, COALESCE(SUM(original_size_bytes),0) AS original FROM sessions").fetchone()
        tracks = conn.execute("SELECT COUNT(DISTINCT track) AS n FROM sessions").fetchone()
    return {
        "sessions": int(sessions["n"]),
        "tracks": int(tracks["n"]),
        "stored_bytes": int(sessions["stored"]),
        "original_bytes": int(sessions["original"]),
        "saved_bytes": int(sessions["original"]) - int(sessions["stored"]),
    }
