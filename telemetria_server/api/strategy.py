"""Strategy endpoints: optimiser (planner) and the post-race review of a stored session."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from telemetry import strategy, tyre_inventory, tyres
from telemetry.compounds import Allocation, c_label, get_allocation
from telemetry.conditions import _as_state
from telemetry.corners import normalize_track_name
from telemetry.strategy import CompoundSpec, Plan, RaceParams

from ..serialization import to_jsonable
from ._common import load_columns, root_of, session_or_404
from .tyres import allocation_payload, default_limit, model_payload

router = APIRouter()

TOP_PLANS = 8
CHART_PLANS = 4
_PARAM_FIELDS = {f.name for f in fields(RaceParams)}


class ParamsIn(BaseModel):
    """Any subset of RaceParams; unset fields keep the model / saved value."""

    model_config = ConfigDict(extra="forbid")

    laps: int | None = None
    pit_loss_s: float | None = None
    base_pace_s: float | None = None
    fuel_per_lap_kg: float | None = None
    fuel_effect_s_per_kg: float | None = None
    fuel_margin_laps: float | None = None
    wear_limit_pct: float | None = None
    sc_pit_factor: float | None = None
    require_two_compounds: bool | None = None
    max_stops: int | None = None
    window_tolerance_s: float | None = None


class SpecIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: int
    use: bool | None = None
    offset_s: float | None = None
    deg_s_per_lap: float | None = None
    wear_pct_per_lap: float | None = None
    warmup_s: float | None = None


class OptimiseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    track: str
    state: str = "dry"
    params: ParamsIn | None = None
    specs: list[SpecIn] | None = None
    use_inventory: bool = True


class TyreSetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compound: int
    wear: float = 0.0
    available: bool = True


class TyreSetsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sets: list[TyreSetIn]


@dataclass
class Inputs:
    track: str
    state: str
    model: tyres.TrackTyreModel
    alloc: Allocation
    specs: list[CompoundSpec]
    params: RaceParams
    saved: bool
    wear_limit: float
    inventory: strategy.Inventory | None = None  # what the optimiser limits the sets to (None = unlimited new)
    inventory_record: dict[str, Any] | None = None  # the stored snapshot, also when not used


def build_inputs(
    root: Path,
    track: str,
    state: str,
    params_in: ParamsIn | None = None,
    specs_in: list[SpecIn] | None = None,
    wear_limit: float | None = None,
    *,
    use_inventory: bool = False,
) -> Inputs:
    """Model defaults, then saved overrides, then request overrides (mirrors the Streamlit planner).

    ``use_inventory``: limit the plan to the stored tyre sets of the track (when there are any).
    """
    track_n = normalize_track_name(track) or track
    alloc = get_allocation(track_n, root)
    limit = wear_limit if wear_limit is not None else default_limit(root)
    model = tyres.track_compound_model(track_n, state, root, wear_limit=limit)
    params = strategy.default_params(model, track_n)
    if model.compounds:
        specs = strategy.specs_from_model(model)
    else:
        from telemetry.compounds import get_game_tyres

        specs = strategy.manual_specs(alloc, get_game_tyres(track_n, root), laps=params.laps, wear_limit=params.wear_limit_pct)
    saved_p, saved_c = strategy.load_overrides(track_n, state, root)
    params, specs = strategy.apply_overrides(params, specs, saved_p, saved_c)
    if params_in is not None:
        params = replace(params, **params_in.model_dump(exclude_none=True))
    if specs_in:
        by_code = {s.code: s for s in specs}
        for item in specs_in:
            if item.code not in by_code:
                raise HTTPException(422, f"Compound {item.code} is not in the {state} model for {track_n}")
            by_code[item.code] = replace(by_code[item.code], **item.model_dump(exclude_none=True, exclude={"code"}), source="manual")
        specs = [by_code[s.code] for s in specs]
    record = tyre_inventory.get_inventory(track_n, root)
    # generic placeholder codes (no allocation known) do not match the game's sets: then no limit
    inv = tyre_inventory.available_wear(record["sets"]) if (use_inventory and record and alloc.source != "none") else None
    return Inputs(track_n, state, model, alloc, specs, params, bool(saved_p or saved_c), limit, inv, record)


def inventory_payload(record: dict[str, Any] | None, used: bool, specs: list[CompoundSpec]) -> dict[str, Any] | None:
    """The stored tyre sets, plus a per-compound summary (new count, used wears) for the planner."""
    if not record:
        return None
    labels = {s.code: s.label for s in specs}
    by: dict[str, dict[str, Any]] = {}
    for code, wears in sorted(tyre_inventory.available_wear(record["sets"]).items()):
        by[str(code)] = {"label": labels.get(code, c_label(code)), "in_model": code in labels,
                         "new": sum(1 for w in wears if w < 0.5), "used": [w for w in wears if w >= 0.5]}
    return {**record, "used": used, "by_compound": by}


def plan_json(plan: Plan, by_code: dict[int, CompoundSpec], best_time: float | None = None) -> dict[str, Any]:
    out = {
        "compounds": list(plan.compounds),
        "stints": list(plan.stints),
        "stops": plan.stops,
        "stop_laps": plan.stop_laps,
        "windows": [list(w) for w in plan.windows],
        "start_wear": list(plan.wears()),
        "race_time": plan.race_time,
        "label": plan.describe(by_code),
    }
    if best_time is not None:
        out["delta_best"] = plan.race_time - best_time
    return out


def params_json(params: RaceParams) -> dict[str, Any]:
    out = {f: getattr(params, f) for f in _PARAM_FIELDS}
    out["start_fuel_kg"] = params.start_fuel_kg
    return out


@router.post("/strategy/optimise")
def optimise(body: OptimiseIn, request: Request) -> Any:
    root = root_of(request)
    inp = build_inputs(root, body.track, body.state, body.params, body.specs, use_inventory=body.use_inventory)
    specs, params, inv = inp.specs, inp.params, inp.inventory
    by_code = {s.code: s for s in specs}
    out: dict[str, Any] = {
        "track": inp.track,
        "state": inp.state,
        "model": model_payload(inp.model, inp.wear_limit),
        "params": params_json(params),
        "specs": specs,
        "notes": {str(c): m.note for c, m in inp.model.compounds.items() if m.note},
        "sources": inp.model.sources,
        "saved_overrides": inp.saved,
        "allocation": allocation_payload(inp.alloc, [s.code for s in specs]),
        "inventory": inventory_payload(inp.inventory_record, inv is not None, specs),
        "plans": [],
        "sensitivity": [],
        "calls": [],
        "race_trace": None,
        "message": None,
    }
    plans = strategy.optimise(specs, params, inv)
    if not plans:
        out["message"] = (
            "No feasible plan with your tyre sets: they do not last to the flag at this wear limit, "
            "or they do not cover two dry compounds. Edit the sets or turn off 'Plan with my sets'."
            if inv is not None else
            "No feasible plan: every compound runs out before the flag at this wear limit, "
            "or the two-compound rule cannot be met."
        )
        return to_jsonable(out)
    best = plans[0]
    shown = strategy.shortlist(plans, TOP_PLANS)
    out["best"] = plan_json(best, by_code, best.race_time)
    out["plans"] = [plan_json(p, by_code, best.race_time) for p in shown]
    out["sensitivity"] = strategy.sensitivity(specs, params, best, inv)
    out["calls"] = strategy.race_calls(best, specs, params, inv)
    best_cum = np.cumsum(strategy.lap_times(shown[0], specs, params))
    traces = []
    for p in shown[:CHART_PLANS]:
        t = strategy.lap_times(p, specs, params)
        traces.append({"label": p.describe(by_code), "lap_times": t, "gap_to_best": np.cumsum(t) - best_cum})
    out["race_trace"] = {"laps": list(range(1, params.laps + 1)), "plans": traces, "box_laps": shown[0].stop_laps}
    return to_jsonable(out)


def _tyre_sets(track: str, root: Path) -> dict[str, Any]:
    track_n = normalize_track_name(track) or track
    return {"track": track_n, "inventory": tyre_inventory.get_inventory(track_n, root)}


@router.get("/tracks/{track}/tyre-sets")
def read_tyre_sets(track: str, request: Request) -> Any:
    return _tyre_sets(track, root_of(request))


@router.put("/tracks/{track}/tyre-sets")
def write_tyre_sets(track: str, body: TyreSetsIn, request: Request) -> Any:
    """Your own list of sets (replaced by the next game snapshot of the track)."""
    root = root_of(request)
    tyre_inventory.save_inventory(track, [s.model_dump() for s in body.sets], source="manual", app_root=root)
    return _tyre_sets(track, root)


@router.delete("/tracks/{track}/tyre-sets")
def delete_tyre_sets(track: str, request: Request) -> Any:
    root = root_of(request)
    tyre_inventory.clear_inventory(track, root)
    return _tyre_sets(track, root)


@router.get("/sessions/{session_id}/strategy-review")
def strategy_review(session_id: int, request: Request, state: str | None = None) -> Any:
    root = root_of(request)
    session = session_or_404(session_id, root)
    try:
        session, _, summary = tyres.session_frames(session_id, root)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    track = normalize_track_name(session.get("track")) or (session.get("track") or "")
    state = state or _as_state(session.get("conditions"))
    pit_cols = load_columns(session_id, root, ["pitIdealLap", "pitLatestLap"])
    windows = strategy.game_pit_windows(pit_cols)
    is_race = not summary.empty and (
        str(session.get("session_type") or "") == "Race"
        or ("pit_stop" in summary.columns and bool(summary["pit_stop"].any()))
    )
    out: dict[str, Any] = {
        "session_id": session_id,
        "track": track,
        "state": state,
        "is_race": is_race,
        "review": None,
        "reason": None,
        "game_pit_windows": [list(w) for w in windows],
    }
    if not is_race:
        out["reason"] = "Open a race session (with pit stops) to compare the strategy that was run with the model optimum."
        return to_jsonable(out)
    inp = build_inputs(root, track, state)
    by_code = {s.code: s for s in inp.specs}
    out["params"] = params_json(inp.params)
    out["allocation"] = allocation_payload(inp.alloc, [s.code for s in inp.specs])
    review = strategy.review_race(summary, inp.specs, inp.params)
    if review is None:
        out["reason"] = strategy.review_unavailable_reason(summary, by_code, inp.params, state)
        return to_jsonable(out)
    actual_times = strategy.lap_times(review.actual, inp.specs, inp.params)
    for lap, t in zip(summary["lap"].astype(int), summary["lap_time"].astype(float)):
        if 0 <= lap < len(actual_times):
            actual_times[lap] = t  # laps the export skipped stay on the model
    out["review"] = {
        "actual": plan_json(review.actual, by_code),
        "actual_time": review.actual_time,
        "model_actual_time": review.model_actual_time,
        "best": plan_json(review.best, by_code),
        "strategy_cost_s": review.strategy_cost_s,
        "execution_s": review.execution_s,
        "missing_laps": review.missing_laps,
        "sc_laps": review.sc_laps,
        "over_limit": [
            {"stint": k, "compound": c, "laps": n, "max_laps": cap} for k, c, n, cap in review.over_limit
        ],
        "actual_lap_times": actual_times,
    }
    return to_jsonable(out)
