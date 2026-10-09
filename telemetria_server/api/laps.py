"""Lap-level analysis endpoints: channels, comparison, map, channel inventory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request

from telemetry import channels as ch
from telemetry import db
from telemetry.corners import normalize_track_name, resolve_corners
from telemetry.map_data import COLOR_CHANNELS, MAP_COLUMNS, lap_map_payload
from telemetry.metrics import align_laps, compute_time_delta, sector_deltas
from telemetry.resample import distance_grid, resample_by_distance

from ..serialization import to_jsonable
from ._common import lap_or_404, load_columns, root_of, session_or_404

router = APIRouter()

DEFAULT_CHANNELS = ("speed", "throttle", "brake", "gear", "rpm", "steering", "lap_time")
EXTRA_UNITS = {"lap_time": "s", "lap_distance": "m"}
BASE_COLUMNS = ("lap", "lap_distance", "bin_index")
COMPARE_CHANNELS = ("lap_time", "speed", "throttle", "brake", "gear", "steering", "rpm")


def _schema(session: dict[str, Any], root: Path):
    import pyarrow.parquet as pq

    path = root / session["telemetry_path"]
    if not path.exists():
        raise HTTPException(404, f"Telemetry file missing for session {session['id']}")
    return pq.read_schema(path)


@router.get("/sessions/{session_id}/laps/{lap}/channels")
def lap_channels(
    session_id: int,
    lap: int,
    request: Request,
    channels: str | None = None,
    step: float = Query(2.0, ge=0.5, le=50.0),
) -> Any:
    root = root_of(request)
    session = session_or_404(session_id, root)
    wanted = [c.strip() for c in (channels.split(",") if channels else DEFAULT_CHANNELS) if c.strip()]
    if not wanted:
        raise HTTPException(400, "No channels requested")
    names = set(_schema(session, root).names)
    unknown = [c for c in wanted if c not in names]
    if unknown:
        raise HTTPException(400, f"Unknown channels: {', '.join(unknown)}")
    df = load_columns(session_id, root, [*wanted, *BASE_COLUMNS])
    focus = lap_or_404(df, lap, session_id)
    if "lap_distance" not in focus.columns:
        raise HTTPException(404, "Session has no lap_distance channel")
    grid = distance_grid(float(focus["lap_distance"].max()), step)
    data = resample_by_distance(focus, wanted, grid)
    units = {}
    for name in wanted:
        known = ch.channel(name)
        units[name] = known.unit if known else EXTRA_UNITS.get(name, "")
    return to_jsonable(
        {
            "session_id": session_id,
            "lap": lap,
            "x": grid,
            "x_label": "Distance (m)",
            "channels": {name: data[name] for name in wanted},
            "units": units,
        }
    )


@router.get("/sessions/{session_id}/compare")
def compare(session_id: int, request: Request, lap: int, ref_lap: int, ref_session: int | None = None) -> Any:
    root = root_of(request)
    session_or_404(session_id, root)
    cols = [*COMPARE_CHANNELS, *BASE_COLUMNS]
    df = load_columns(session_id, root, cols)
    focus_df = lap_or_404(df, lap, session_id)
    ref_id = ref_session if ref_session is not None else session_id
    if ref_id != session_id:
        session_or_404(ref_id, root)
        ref_all = load_columns(ref_id, root, cols)
    else:
        ref_all = df
    ref_df = lap_or_404(ref_all, ref_lap, ref_id)
    try:
        aligned = compute_time_delta(align_laps(ref_df, focus_df, list(COMPARE_CHANNELS)))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if aligned.empty:
        raise HTTPException(404, "Nothing to compare")
    out: dict[str, Any] = {"session_id": session_id, "lap": lap, "ref_session": ref_id, "ref_lap": ref_lap}
    out["lap_distance"] = aligned["lap_distance"]
    for name in COMPARE_CHANNELS:
        for prefix in ("ref", "cmp"):
            col = f"{prefix}_{name}"
            if col in aligned.columns:
                out[col] = aligned[col]
    out["delta_time"] = aligned["delta_time"]
    finite = aligned["delta_time"].to_numpy(dtype=float)
    finite = finite[np.isfinite(finite)]
    out["final_delta"] = float(finite[-1]) if finite.size else None
    out["sectors"] = sector_deltas(aligned, 3)
    out["mini_sectors"] = sector_deltas(aligned, 12).rename(columns={"sector": "mini_sector"})
    return to_jsonable(out)


@router.get("/sessions/{session_id}/map")
def track_map(
    session_id: int,
    request: Request,
    lap: int,
    ref_lap: int | None = None,
    color: str = "speed",
    step: float = Query(2.0, ge=0.5, le=50.0),
) -> Any:
    if color not in COLOR_CHANNELS:
        raise HTTPException(400, f"color must be one of {', '.join(COLOR_CHANNELS)}")
    root = root_of(request)
    session = session_or_404(session_id, root)
    cols = [*MAP_COLUMNS, "pos_x", "pos_y", "pos_z", "trackLength", *BASE_COLUMNS]
    df = load_columns(session_id, root, cols)
    focus_df = lap_or_404(df, lap, session_id)
    ref_df = lap_or_404(df, ref_lap, session_id) if ref_lap is not None and ref_lap != lap else None

    track = normalize_track_name(session.get("track"))
    if "trackLength" in df.columns and df["trackLength"].notna().any():
        track_length = float(df["trackLength"].dropna().iloc[0])
    elif session.get("track_length"):
        track_length = float(session["track_length"])
    elif "lap_distance" in df.columns:
        track_length = float(df["lap_distance"].max())
    else:
        track_length = None
    corners = resolve_corners(track, track_length, focus_df)
    raw_track = session.get("track")
    outline = (db.get_track_outline(raw_track, root) if raw_track else None) or (
        db.get_track_outline(track, root) if track else None
    )
    payload = lap_map_payload(
        focus_df,
        ref_df=ref_df,
        color=color,
        outline=outline,
        corners=corners,
        step_m=step,
        cmp_label=f"L{lap}",
        ref_label=f"L{ref_lap}" if ref_df is not None else "Ref",
    )
    payload.update(
        {
            "session_id": session_id,
            "lap": lap,
            "ref_lap": ref_lap if ref_df is not None else None,
            "track": track,
            "track_length": track_length,
        }
    )
    return to_jsonable(payload)


@router.get("/sessions/{session_id}/channels/inventory")
def channel_inventory(session_id: int, request: Request) -> Any:
    root = root_of(request)
    session = session_or_404(session_id, root)
    frame = _schema(session, root).empty_table().to_pandas()  # names + dtypes are all inventory needs
    return to_jsonable(ch.inventory(frame))
