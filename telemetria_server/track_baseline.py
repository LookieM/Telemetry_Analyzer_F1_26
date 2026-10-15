"""Track baseline: resolve a setup from a duel winner, engineer test, library session or raw values, and store it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from telemetry import corner_store, db, duel_store, engineer_log
from telemetry.garage import to_garage
from telemetry.garage_display import garage_display
from telemetry.setup_eval import load_session_runs
from telemetry.setup_history import compute_setup_fingerprint, mech_fingerprint, parse_setup_json


class BaselineError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


def session_setup(session_id: int, root: Path) -> dict[str, Any]:
    session = db.get_session(session_id, root)
    if not session:
        raise BaselineError(404, f"Session {session_id} not found")
    setup = to_garage(parse_setup_json(session.get("setup_json")))
    if not setup:
        for run in load_session_runs(session_id, root):
            if run.setup:
                setup = to_garage(run.setup)
                break
    if not setup:
        raise BaselineError(422, f"Session {session_id} has no garage setup")
    return setup


def _duel_setup(track: str, duel_id: int, winner_key: str, root: Path) -> tuple[dict[str, Any], str]:
    duel = duel_store.get_duel(duel_id, root)
    if not duel:
        raise BaselineError(404, f"Duel {duel_id} not found")
    result = duel["result"]
    if winner_key not in (result.get("fingerprints") or []):
        raise BaselineError(422, f"{winner_key} was not a contestant of duel {duel_id}")
    sessions = [s for s in corner_store.track_sessions(track, root)]
    sessions.sort(key=lambda s: str(s.get("created_at") or ""), reverse=True)
    for s in sessions:
        try:
            runs = load_session_runs(int(s["id"]), root)
        except FileNotFoundError:
            continue
        for run in runs:
            if run.mech_fp == winner_key and run.setup:
                return to_garage(run.setup), str(result.get("names", {}).get(winner_key) or "")
    raise BaselineError(404, f"No library session has setup {winner_key}")


def _clean_setup(setup: Any) -> dict[str, Any]:
    if not isinstance(setup, dict) or not setup:
        raise BaselineError(422, "setup must be a non-empty object")
    try:
        out = to_garage({k: float(v) for k, v in setup.items()})
    except (TypeError, ValueError) as exc:
        raise BaselineError(422, "setup values must be numbers") from exc
    if not out:
        raise BaselineError(422, "setup has no garage values")
    return out


def payload(track: str, root: Path) -> dict[str, Any]:
    data = duel_store.get_baselines(track, root)
    rows = [{**r, "display": garage_display(r["setup"])} for r in data["history"]]
    return {"track": track, "active": next((r for r in rows if r["active"]), None), "history": rows}


def set_from(track: str, body: dict[str, Any], root: Path) -> dict[str, Any]:
    """Apply one POST body (see the API) and return ``payload``. Raises BaselineError."""
    if body.get("restore_id") is not None:
        if duel_store.restore_baseline(track, int(body["restore_id"]), root) is None:
            raise BaselineError(404, f"Baseline {body['restore_id']} not found on {track}")
        return payload(track, root)
    name = (body.get("name") or "").strip()
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else None
    if body.get("duel_id") is not None:
        if not body.get("winner_key"):
            raise BaselineError(422, "winner_key is required with duel_id")
        setup, label = _duel_setup(track, int(body["duel_id"]), str(body["winner_key"]), root)
        source, ref = "duel", int(body["duel_id"])
        name = name or label or f"Duel #{ref} winner"
        meta = {**(meta or {}), "winner_key": body["winner_key"]}
    elif body.get("engineer_test_id") is not None:
        ref = int(body["engineer_test_id"])
        test = next((t for t in engineer_log.list_tests(None, root) if t["id"] == ref), None)
        if not test:
            raise BaselineError(404, f"Engineer test {ref} not found")
        setup = _clean_setup(json.loads(test["final_json"] or "{}"))
        source = "engineer"
        name = name or f"Engineer test #{ref}"
    elif body.get("session_id") is not None:
        ref = int(body["session_id"])
        setup = session_setup(ref, root)
        source = "library"
        name = name or f"Session #{ref}"
    elif body.get("setup") is not None:
        setup = _clean_setup(body["setup"])
        source = str(body.get("source") or "manual")
        if source not in ("manual", "generator", "engineer"):
            raise BaselineError(422, "source must be manual, generator or engineer")
        ref = None
        name = name or {"manual": "Manual setup", "generator": "Generated setup", "engineer": "Engineer setup"}[source]
    else:
        raise BaselineError(422, "Give one of duel_id+winner_key, engineer_test_id, session_id, setup or restore_id")
    duel_store.set_baseline(track, setup, source=source, name=name[:80], ref_id=ref, meta=meta,
                            fingerprint=mech_fingerprint(setup) or compute_setup_fingerprint(setup), app_root=root)
    return payload(track, root)
