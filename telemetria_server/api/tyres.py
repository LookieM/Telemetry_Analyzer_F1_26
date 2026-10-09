"""Tyre endpoints: per-session stint analysis and the per-track compound model."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from telemetry import channels, tyres
from telemetry.compounds import Allocation, get_allocation
from telemetry.corners import normalize_track_name

from ..serialization import to_jsonable
from ._common import root_of, session_or_404

router = APIRouter()


def default_limit(root: Path) -> float:
    return tyres.default_wear_limit(tyres.library_race_stats(root))


def allocation_payload(alloc: Allocation, codes: list[int | None] | None = None) -> dict[str, Any]:
    """{code: {label, role, color}} for the allocation's compounds plus any extra codes."""
    seen = {int(c) for c in alloc.roles} | {int(c) for c in (codes or []) if c is not None}
    return {
        str(c): {"label": alloc.label(c), "role": alloc.role(c), "color": alloc.color(c)} for c in sorted(seen)
    }


def model_payload(model: tyres.TrackTyreModel, wear_limit: float) -> dict[str, Any]:
    out = to_jsonable(model)
    out["pit_loss"] = to_jsonable(model.pit_loss)
    out["sc_pit_factor"] = to_jsonable(model.sc_pit_factor)
    out["wear_limit"] = wear_limit
    for code, comp in model.compounds.items():
        out["compounds"][str(code)]["max_laps"] = comp.max_laps(wear_limit)
    return out


@router.get("/sessions/{session_id}/tyres")
def session_tyres(session_id: int, request: Request, wear_limit: float | None = Query(None, ge=1, le=100)) -> Any:
    root = root_of(request)
    session_or_404(session_id, root)
    try:
        session, df, summary = tyres.session_frames(session_id, root)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    stats = tyres.library_race_stats(root)
    limit = wear_limit if wear_limit is not None else tyres.default_wear_limit(stats)
    track = normalize_track_name(session.get("track")) or (session.get("track") or "")
    alloc = get_allocation(track, root)

    stints = tyres.tyre_stints(summary)
    temp_src = channels.primary_tyre_temp(df)
    kind = channels.temp_kind(temp_src[0] if temp_src else None)
    codes = sorted({s.compound for s in stints if s.compound is not None})
    targets_by_code = {c: tyres.get_targets(c, root, kind=kind) for c in codes}
    longest = max(stints, key=lambda s: s.n_laps, default=None)
    table_targets = targets_by_code.get(longest.compound) if longest is not None else None
    summaries, tbl = tyres.summarize_stints(
        df, summary, session=session, wear_limit=limit, targets=table_targets, fuel_k=stats.fuel_s_per_kg
    )

    stint_rows = []
    for s in summaries:
        code = s.stint.compound
        row = to_jsonable(s)
        targets = targets_by_code.get(code) or tyres.get_targets(code, root, kind=kind)
        row["label"] = alloc.label(code)
        row["role"] = alloc.role(code)
        row["color"] = alloc.color(code)
        row["targets"] = to_jsonable(targets)
        row["pressure"] = to_jsonable(tyres.pressure_recommendation(s.hot_psi, s.cold_psi, targets))
        stint_rows.append(row)

    return to_jsonable(
        {
            "session_id": session_id,
            "track": track,
            "wear_limit": limit,
            "temp_channel": temp_src[0] if temp_src else None,
            "temp_kind": kind,
            "stints": stint_rows,
            "wheel_table": tbl,
            "targets": {str(c): t for c, t in targets_by_code.items()},
            "allocation": allocation_payload(alloc, codes),
            "race_stats": asdict(stats),
        }
    )


@router.get("/tracks/{track}/compound-model")
def compound_model(track: str, request: Request, state: str = "dry", wear_limit: float | None = Query(None, ge=1, le=100)) -> Any:
    root = root_of(request)
    track_n = normalize_track_name(track) or track
    limit = wear_limit if wear_limit is not None else default_limit(root)
    model = tyres.track_compound_model(track_n, state, root, wear_limit=limit)
    return model_payload(model, limit)
