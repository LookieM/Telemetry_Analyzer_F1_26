"""Import SRT CSV exports into the compact session library."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .db import (
    compact_dataframe,
    default_data_dir,
    extract_track_outline,
    file_hash,
    find_by_hash,
    insert_imported_session,
    upsert_track_map,
)
from .insights import generate_insights
from .garage import garage_from_raw
from .loader import load_telemetry, mean_setup, setup_from_telemetry
from .metrics import MIN_VALID_LAP_S, build_lap_summary, session_meta


@dataclass
class ImportResult:
    session_id: int
    already_existed: bool
    source_name: str
    track: str | None
    car: str | None
    lap_count: int
    original_bytes: int
    stored_bytes: int
    source_deleted: bool
    message: str


def import_csv(
    csv_path: str | Path,
    *,
    app_root: Path | None = None,
    delete_source: bool = False,
    notes: str = "",
    session_type: str = "",
    conditions: str = "",
    source_name: str | None = None,
) -> ImportResult:
    """
    Load a raw SRT CSV, store compact Parquet + SQLite metadata, optionally delete the CSV.

    Typical size drop: ~230 MB race CSV → ~70 MB Parquet with every numeric channel kept.
    A blank session type / track state is inferred from the file name and the telemetry.
    `source_name` overrides the stored file name (uploads land in a temp file).
    """
    root = app_root or Path(__file__).resolve().parent.parent
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(path)

    original_size = path.stat().st_size
    digest = file_hash(path)

    existing = find_by_hash(digest, root)
    if existing:
        return _existing_result(existing, original_size)

    df = load_telemetry(path)
    return ingest_dataframe(
        df,
        source_name=source_name or path.name,
        source_hash=digest,
        original_size=original_size,
        app_root=root,
        session_type=session_type,
        conditions=conditions,
        notes=notes,
        delete_source_path=path if delete_source else None,
    )


def ingest_dataframe(
    df: pd.DataFrame,
    *,
    source_name: str,
    source_hash: str,
    original_size: int,
    app_root: Path | None = None,
    session_type: str = "",
    conditions: str = "",
    notes: str = "",
    delete_source_path: Path | None = None,
) -> ImportResult:
    """
    Store an already loaded telemetry frame: meta, lap summary, setup, tags, compact Parquet,
    DB rows, track outline, progress and the setup journal. Shared by CSV import and live recording.
    An existing `source_hash` is not stored twice; the existing session is returned.
    """
    root = app_root or Path(__file__).resolve().parent.parent
    digest = source_hash
    existing = find_by_hash(digest, root)
    if existing:
        return _existing_result(existing, original_size)

    if df.empty or "lap" not in df.columns:
        raise ValueError("Could not parse lap telemetry from this file.")

    meta = session_meta(df)
    summary = build_lap_summary(df, track_length=meta.get("track_length"))
    if summary.empty:
        raise ValueError(
            f"No probable completed laps found (need ~{MIN_VALID_LAP_S:.0f}s+ flying laps with full distance; "
            "takebacks / red-flag partials are ignored)."
        )

    setup = setup_from_telemetry(df, int(summary.loc[summary["is_best"], "lap"].iloc[0]))
    if not setup:
        setup = garage_from_raw(mean_setup(df))
    from .setup_history import compute_setup_fingerprint

    setup_fp = compute_setup_fingerprint(setup)
    name = source_name
    if not session_type or not conditions:
        from .session_tags import infer_tags

        auto_type, auto_cond = infer_tags(name, summary)
        session_type = session_type or auto_type
        conditions = conditions or auto_cond
    compact = compact_dataframe(df)

    data_dir = default_data_dir(root)
    # Stable file name from hash prefix
    tel_name = f"session_{digest[:12]}.parquet"
    tel_path = data_dir / "sessions" / tel_name
    compact.to_parquet(tel_path, compression="zstd", index=False)
    stored_size = tel_path.stat().st_size

    # Precompute coaching notes vs best lap for each lap
    best_lap = int(summary.loc[summary["is_best"], "lap"].iloc[0])
    track = meta.get("track")
    track_length = meta.get("track_length")
    if track_length is not None:
        try:
            track_length = float(track_length)
        except (TypeError, ValueError):
            track_length = None
    insights_by_lap: dict[int, list[dict]] = {}
    for lap in summary["lap"].tolist():
        notes_list = generate_insights(
            df,
            int(lap),
            reference_lap=best_lap,
            track=track,
            track_length=track_length,
        )
        insights_by_lap[int(lap)] = [
            {
                "severity": n.severity,
                "title": n.title,
                "detail": n.detail,
                "category": n.category,
            }
            for n in notes_list
        ]

    relpath = str(Path("data") / "sessions" / tel_name)
    session_id = insert_imported_session(
        source_name=name,
        source_hash=digest,
        meta=meta,
        summary=summary,
        insights_by_lap=insights_by_lap,
        setup=setup,
        telemetry_relpath=relpath.replace("\\", "/"),
        original_size=original_size,
        stored_size=stored_size,
        source_deleted=False,
        app_root=root,
        notes=notes,
        session_type=session_type,
        conditions=conditions,
        setup_fingerprint=setup_fp,
    )

    outline = extract_track_outline(df)
    if meta.get("track"):
        upsert_track_map(str(meta["track"]), outline, session_id, root)

    from .progress import record_session_progress

    progress = record_session_progress(
        session_id,
        df,
        summary,
        root,
        track_hint=meta.get("track"),
        car_hint=meta.get("car"),
        track_length_hint=meta.get("track_length"),
    )

    if meta.get("track"):
        # Score earlier setup advice and experiments against this new session.
        try:
            from .setup_log import evaluate_track

            evaluate_track(str(meta["track"]), root)
        except Exception:
            pass  # the journal is a bonus; never fail an import because of it

    source_deleted = False
    if delete_source_path is not None:
        delete_source_path.unlink()
        source_deleted = True
        from .db import connect

        with connect(root) as conn:
            conn.execute(
                "UPDATE sessions SET source_deleted = 1 WHERE id = ?",
                (session_id,),
            )

    saved = original_size - stored_size
    pb_note = " New personal best!" if progress.get("pb_updated") else ""
    tag_note = f" Tagged {session_type}." if session_type else ""
    return ImportResult(
        session_id=session_id,
        already_existed=False,
        source_name=name,
        track=meta.get("track"),
        car=meta.get("car"),
        lap_count=len(summary),
        original_bytes=original_size,
        stored_bytes=stored_size,
        source_deleted=source_deleted,
        message=(
            f"Imported session #{session_id}: "
            f"{_mb(original_size)} -> {_mb(stored_size)} "
            f"(saved {_mb(saved)})."
            + (" Source CSV deleted." if source_deleted else "")
            + pb_note
            + tag_note
        ),
    )


def _existing_result(existing: dict, original_size: int) -> ImportResult:
    return ImportResult(
        session_id=int(existing["id"]),
        already_existed=True,
        source_name=existing["source_name"],
        track=existing.get("track"),
        car=existing.get("car"),
        lap_count=int(existing.get("lap_count") or 0),
        original_bytes=int(existing.get("original_size_bytes") or original_size),
        stored_bytes=int(existing.get("stored_size_bytes") or 0),
        source_deleted=False,
        message=f"Already in library as session #{existing['id']}.",
    )


def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):.1f} MB"
