"""Lap-level analysis endpoints: channels, comparison, map, channel inventory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request

from telemetry import channels as ch
from telemetry import corner_store, db, lap_extras
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


def _extras(keys: str | None, names) -> dict[str, str]:
    """Requested extra keys -> {output name: stored column} for a session's column names (400 on an unknown key)."""
    wanted = [k.strip() for k in (keys.split(",") if keys else []) if k.strip()]
    unknown = [k for k in wanted if k not in lap_extras.BY_KEY]
    if unknown:
        raise HTTPException(400, f"Unknown extras: {', '.join(unknown)}")
    mapping: dict[str, str] = {}
    for key in dict.fromkeys(wanted):
        mapping.update(lap_extras.resolve(lap_extras.BY_KEY[key], names))
    return mapping


def _with_extras(df, mapping: dict[str, str]):
    """Copy each extra's stored column under its API output name (e.g. slip_angle_FL)."""
    for out_name, col in mapping.items():
        df[out_name] = df[col]
    return df


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
    extras: str | None = None,
    step: float = Query(2.0, ge=0.5, le=50.0),
) -> Any:
    root = root_of(request)
    session = session_or_404(session_id, root)
    wanted = [c.strip() for c in (channels.split(",") if channels is not None else DEFAULT_CHANNELS) if c.strip()]
    if not wanted and not extras:
        raise HTTPException(400, "No channels requested")
    names = set(_schema(session, root).names)
    extra_cols = _extras(extras, names)
    unknown = [c for c in wanted if c not in names]
    if unknown:
        raise HTTPException(400, f"Unknown channels: {', '.join(unknown)}")
    df = load_columns(session_id, root, [*wanted, *extra_cols.values(), *BASE_COLUMNS])
    focus = lap_or_404(df, lap, session_id)
    if "lap_distance" not in focus.columns:
        raise HTTPException(404, "Session has no lap_distance channel")
    grid = distance_grid(float(focus["lap_distance"].max()), step)
    data = resample_by_distance(focus, [*wanted, *extra_cols.values()], grid)
    for out_name, col in extra_cols.items():
        data[out_name] = data[col]
        wanted.append(out_name)
    units = {}
    for name in wanted:
        known = ch.channel(name)
        units[name] = known.unit if known else EXTRA_UNITS.get(name, "")
    for extra in lap_extras.EXTRAS:
        for out_name in lap_extras.output_names(extra):
            if out_name in units:
                units[out_name] = extra.unit
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


@router.get("/sessions/{session_id}/lap-extras")
def lap_extra_channels(session_id: int, request: Request) -> Any:
    """The optional lap-trace channels (g-forces, per-wheel slip / temps) and whether this session has data for each."""
    root = root_of(request)
    session = session_or_404(session_id, root)
    names = _schema(session, root).names
    return lap_extras.availability(names, lambda cols: load_columns(session_id, root, cols))


@router.get("/sessions/{session_id}/compare")
def compare(
    session_id: int, request: Request, lap: int, ref_lap: int, ref_session: int | None = None, extras: str | None = None
) -> Any:
    root = root_of(request)
    session = session_or_404(session_id, root)
    own_cols = _extras(extras, _schema(session, root).names)
    df = _with_extras(load_columns(session_id, root, [*COMPARE_CHANNELS, *own_cols.values(), *BASE_COLUMNS]), own_cols)
    focus_df = lap_or_404(df, lap, session_id)
    ref_id = ref_session if ref_session is not None else session_id
    if ref_id != session_id:
        ref_meta = session_or_404(ref_id, root)
        ref_cols = _extras(extras, _schema(ref_meta, root).names)
        ref_all = _with_extras(load_columns(ref_id, root, [*COMPARE_CHANNELS, *ref_cols.values(), *BASE_COLUMNS]), ref_cols)
    else:
        ref_all = df
    ref_df = lap_or_404(ref_all, ref_lap, ref_id)
    all_channels = [*COMPARE_CHANNELS, *own_cols]
    try:
        aligned = compute_time_delta(align_laps(ref_df, focus_df, all_channels))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if aligned.empty:
        raise HTTPException(404, "Nothing to compare")
    out: dict[str, Any] = {"session_id": session_id, "lap": lap, "ref_session": ref_id, "ref_lap": ref_lap}
    out["lap_distance"] = aligned["lap_distance"]
    for name in all_channels:
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


def _stored_corner_marks(track: str | None, root: Path):
    """Corner spans / labels from the stored track corners (the Corners tab's set); (None, None) falls back to the catalogue."""
    if not track:
        return None, None
    try:
        corners = corner_store.ensure_track_corners(track, root)["corners"]
    except Exception:  # no clean lap, detection failure, ...: the old catalogue spans still work
        return None, None
    spans = [{"from": float(c["start_m"]), "to": float(c["end_m"]), "name": c["name"]} for c in corners]
    labels = [{"text": c["name"], "d": float(c["apex_m"])} for c in corners if c.get("apex_m") is not None]
    return spans, labels


@router.get("/sessions/{session_id}/map")
def track_map(
    session_id: int,
    request: Request,
    lap: int,
    ref_lap: int | None = None,
    ref_session: int | None = None,
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
    ref_id = ref_session if ref_session is not None else session_id
    ref_df = None
    if ref_lap is not None and (ref_id != session_id or ref_lap != lap):
        if ref_id != session_id:
            session_or_404(ref_id, root)
            ref_all = load_columns(ref_id, root, [*MAP_COLUMNS, *BASE_COLUMNS])
        else:
            ref_all = df
        ref_df = lap_or_404(ref_all, ref_lap, ref_id)

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
    spans, labels = _stored_corner_marks(track, root)
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
    if spans is not None:
        payload["spans"], payload["labels"] = spans, labels
    payload.update(
        {
            "session_id": session_id,
            "lap": lap,
            "ref_lap": ref_lap if ref_df is not None else None,
            "ref_session": ref_id if ref_df is not None else None,
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
