"""Editable settings: tyre allocation per track, tyre targets per compound, strategy overrides."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from telemetry import strategy, tyres
from telemetry.compounds import ACTUAL_COMPOUNDS, SLICK_CODES, clear_allocation, get_allocation, set_allocation, softness
from telemetry.corners import normalize_track_name

from ..serialization import to_jsonable
from ._common import root_of
from .strategy import ParamsIn, SpecIn, build_inputs
from .tyres import allocation_payload

router = APIRouter()


class AllocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    soft: int | None = None
    medium: int | None = None
    hard: int | None = None


class TargetsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temp_lo: float = Field(ge=0, le=300)
    temp_hi: float = Field(ge=0, le=300)
    hot_front_psi: float | None = Field(None, ge=0, le=60)
    hot_rear_psi: float | None = Field(None, ge=0, le=60)


class OverridesIn(BaseModel):
    """Partial params / specs are applied on top of the model defaults, then stored in full."""

    model_config = ConfigDict(extra="forbid")

    state: str = "dry"
    params: ParamsIn | None = None
    specs: list[SpecIn] | None = None


def _allocation(track: str, request: Request) -> dict[str, Any]:
    root = root_of(request)
    track_n = normalize_track_name(track) or track
    alloc = get_allocation(track_n, root)
    inv = {role: code for code, role in alloc.roles.items()}
    return to_jsonable(
        {
            "track": alloc.track,
            "source": alloc.source,
            "soft": inv.get("S"),
            "medium": inv.get("M"),
            "hard": inv.get("H"),
            "roles": {str(c): r for c, r in alloc.roles.items()},
            "compounds": allocation_payload(alloc),
            # Slick compounds a track can nominate, softest first (for the S / M / H pickers).
            "options": [
                {"code": c, "label": ACTUAL_COMPOUNDS[c]} for c in sorted(SLICK_CODES, key=softness, reverse=True)
            ],
        }
    )


@router.get("/tracks/{track}/allocation")
def read_allocation(track: str, request: Request) -> Any:
    return _allocation(track, request)


@router.put("/tracks/{track}/allocation")
def write_allocation(track: str, body: AllocationIn, request: Request) -> Any:
    set_allocation(track, body.soft, body.medium, body.hard, root_of(request))
    tyres.clear_cache()
    return _allocation(track, request)


@router.delete("/tracks/{track}/allocation")
def delete_allocation(track: str, request: Request) -> Any:
    clear_allocation(track, root_of(request))
    tyres.clear_cache()
    return _allocation(track, request)


@router.get("/compounds/{code}/targets")
def read_targets(code: int, request: Request, kind: str = "surface") -> Any:
    return to_jsonable(tyres.get_targets(code, root_of(request), kind=kind))


@router.put("/compounds/{code}/targets")
def write_targets(code: int, body: TargetsIn, request: Request, kind: str = "surface") -> Any:
    root = root_of(request)
    tyres.save_targets(
        tyres.TyreTargets(code, body.temp_lo, body.temp_hi, body.hot_front_psi, body.hot_rear_psi, "saved"), root
    )
    tyres.clear_cache()
    return to_jsonable(tyres.get_targets(code, root, kind=kind))


def _overrides(track: str, state: str, request: Request) -> dict[str, Any]:
    params, comps = strategy.load_overrides(track, state, root_of(request))
    return to_jsonable(
        {
            "track": normalize_track_name(track) or track,
            "state": state,
            "saved": bool(params or comps),
            "params": params,
            "compounds": comps,
        }
    )


@router.get("/tracks/{track}/strategy-overrides")
def read_overrides(track: str, request: Request, state: str = "dry") -> Any:
    return _overrides(track, state, request)


@router.put("/tracks/{track}/strategy-overrides")
def write_overrides(track: str, body: OverridesIn, request: Request) -> Any:
    root = root_of(request)
    inp = build_inputs(root, track, body.state, body.params, body.specs)
    strategy.save_overrides(inp.track, body.state, inp.params, inp.specs, root)
    tyres.clear_cache()
    return _overrides(track, body.state, request)


@router.delete("/tracks/{track}/strategy-overrides")
def delete_overrides(track: str, request: Request, state: str = "dry") -> Any:
    strategy.clear_overrides(track, state, root_of(request))
    tyres.clear_cache()
    return _overrides(track, state, request)
