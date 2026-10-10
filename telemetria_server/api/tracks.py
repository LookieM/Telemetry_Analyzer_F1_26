"""The F1 26 track catalog: every circuit with its 50% race distance, tyre allocation and what you have on it."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from telemetry.compounds import c_label, get_allocation, get_game_tyres
from telemetry.corners import normalize_track_name
from telemetry.db import connect, list_sessions
from telemetry.track_catalog import (DEFAULT_PIT_LOSS_S, PIT_LOSS_FALLBACK_S, RACE_LAPS_FULL, RACE_SHARE,
                                     TRACK_CORNERS_FRAC, TRACK_LENGTHS_M, catalog_track_names, race_laps)

from ..serialization import to_jsonable
from ._common import root_of

router = APIRouter()


@router.get("/tracks")
def tracks(request: Request) -> Any:
    root = root_of(request)
    sessions = list_sessions(root)
    counts: dict[str, int] = {}
    if not sessions.empty:
        for t in sessions["track"].dropna():
            name = normalize_track_name(t) or t
            counts[name] = counts.get(name, 0) + 1
    with connect(root) as conn:
        maps = {normalize_track_name(r["track"]) or r["track"] for r in conn.execute("SELECT track FROM track_maps")}
    out = []
    for name in catalog_track_names():
        alloc = get_allocation(name, root)
        inv = {role: code for code, role in alloc.roles.items()}
        game = get_game_tyres(name, root)
        out.append({
            "track": name,
            "length_m": TRACK_LENGTHS_M.get(name),
            "full_laps": RACE_LAPS_FULL.get(name),
            "race_laps": race_laps(name),
            "pit_loss_s": PIT_LOSS_FALLBACK_S.get(name, DEFAULT_PIT_LOSS_S),
            "sessions": counts.get(name, 0),
            "map": name in maps,
            "named_corners": name in TRACK_CORNERS_FRAC,
            "allocation": {
                "source": alloc.source,
                "soft": c_label(inv.get("S")) if inv.get("S") else None,
                "medium": c_label(inv.get("M")) if inv.get("M") else None,
                "hard": c_label(inv.get("H")) if inv.get("H") else None,
            },
            "game_tyres": bool(game),
        })
    return to_jsonable({"race_share": RACE_SHARE, "tracks": out})
