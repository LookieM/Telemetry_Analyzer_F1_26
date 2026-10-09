"""A/B evaluation of two runs (usually the same track, consecutive sessions, different garage)."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .corners import analyze_lap_corners, compare_corners, normalize_track_name, resolve_corners
from .db import ANALYSIS_COLUMNS, get_session, load_session_telemetry
from .metrics import get_lap
from .runs import Run, best_run, split_runs
from .setup_history import diff_setups, list_track_sessions, mech_setup

PHASES = ("entry", "mid", "exit")
# Minimum pace difference we are willing to believe between two sessions. Quali is high on purpose:
# Catalunya Q2 -> Q3 ran the identical garage and still moved 0.59s (driver / track evolution).
NOISE_FLOOR = {"quali": 0.25, "race": 0.10}
MIN_LAPS = {"quali": 2, "race": 3}
# Phase-score improvement (|score| shrinking) that counts as a fixed / worsened symptom.
SYMPTOM_STEP = 0.15
FUEL_WARN_KG = 20.0


@dataclass
class RunComparison:
    mode: str
    session_a_id: int | None
    session_b_id: int | None
    run_a: Run
    run_b: Run
    setup_diff: list[dict[str, Any]]
    pace_delta: float | None  # b - a, negative = b faster (fuel-corrected)
    noise: float
    deg_delta: float | None
    balance_delta: dict[str, float]  # b - a per phase score
    symptom_phases: list[str]
    symptom_delta: float | None  # >0 = diagnosed symptom shrank
    symptom_fixed: bool
    symptom_worse: bool
    temp_delta: dict[str, float]
    lockup_delta: float | None
    wear_delta: float | None
    corner_deltas: list[dict[str, Any]] = field(default_factory=list)
    verdict: str = "inconclusive"  # better | worse | neutral | inconclusive
    verdict_reason: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def changed_keys(self) -> list[str]:
        return [d["key"] for d in self.setup_diff]


def _pace(run: Run, mode: str) -> float:
    return run.best_corrected if mode == "quali" else run.median_corrected


def _noise(a: Run, b: Run, mode: str) -> float:
    se = float(np.sqrt(a.lap_std**2 / max(a.n_laps, 1) + b.lap_std**2 / max(b.n_laps, 1)))
    return max(NOISE_FLOOR.get(mode, 0.10), se)


def _diagnosed_phases(balance: dict[str, Any]) -> list[str]:
    issue = balance.get("issue")
    if not balance or issue in (None, "balanced"):
        return []
    phase = str(balance.get("issue_phase") or "all")
    if phase == "entry+exit":
        return ["entry", "exit"]
    if phase in PHASES:
        return [phase]
    scores = {p: abs(float(balance.get(f"{p}_score") or 0.0)) for p in PHASES}
    return [max(scores, key=scores.get)]


def _symptom_change(a: Run, b: Run) -> tuple[list[str], float | None, bool, bool]:
    phases = _diagnosed_phases(a.balance)
    if not phases or not b.balance:
        return phases, None, False, False
    gains = [abs(float(a.balance.get(f"{p}_score") or 0.0)) - abs(float(b.balance.get(f"{p}_score") or 0.0)) for p in phases]
    delta = float(np.mean(gains))
    cleared = b.balance.get("issue") == "balanced"
    return phases, delta, bool(delta >= SYMPTOM_STEP or cleared), bool(delta <= -SYMPTOM_STEP)


def _corner_deltas(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    run_a: Run,
    run_b: Run,
    track: str | None,
    track_length: float | None,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Biggest corner time swings between the two best laps (positive = b slower)."""
    lap_a, lap_b = get_lap(df_a, run_a.best_lap), get_lap(df_b, run_b.best_lap)
    if lap_a.empty or lap_b.empty:
        return []
    corners = resolve_corners(track, track_length, lap_b)
    cmp = compare_corners(
        analyze_lap_corners(lap_b, track, track_length, corners=corners),
        analyze_lap_corners(lap_a, track, track_length, corners=corners),
    )
    if cmp.empty or "delta_s" not in cmp.columns:
        return []
    cmp = cmp.assign(delta_s=pd.to_numeric(cmp["delta_s"], errors="coerce"))
    cmp = cmp[cmp["delta_s"].notna()]
    rows = []
    for _, r in pd.concat([cmp.nsmallest(top_n, "delta_s"), cmp.nlargest(top_n, "delta_s")]).drop_duplicates("corner_id").iterrows():
        if abs(float(r["delta_s"])) < 0.02:
            continue
        rows.append({"corner": str(r.get("corner_name") or r.get("corner_id")), "delta_s": float(r["delta_s"])})
    rows.sort(key=lambda x: x["delta_s"])
    return rows


def compare_runs(
    a: Run,
    b: Run,
    *,
    mode: str,
    session_a: dict[str, Any] | None = None,
    session_b: dict[str, Any] | None = None,
    corner_deltas: list[dict[str, Any]] | None = None,
) -> RunComparison:
    """Compare run `a` (earlier) with run `b` (later). Everything is b minus a."""
    noise = _noise(a, b, mode)
    pace_delta = _pace(b, mode) - _pace(a, mode)
    deg_delta = (
        b.deg_s_per_lap - a.deg_s_per_lap if a.deg_s_per_lap is not None and b.deg_s_per_lap is not None else None
    )
    balance_delta = {
        p: float(b.balance[f"{p}_score"]) - float(a.balance[f"{p}_score"])
        for p in PHASES
        if f"{p}_score" in a.balance and f"{p}_score" in b.balance
    }
    phases, sym_delta, fixed, worse = _symptom_change(a, b)
    temp_delta = {}
    for key in ("temp_front", "temp_rear"):
        va, vb = getattr(a, key), getattr(b, key)
        if va is not None and vb is not None:
            temp_delta[key] = float(vb - va)
    lockup_delta = (
        b.lockup_frac - a.lockup_frac if a.lockup_frac is not None and b.lockup_frac is not None else None
    )
    wear_delta = (
        b.wear_pct_per_lap - a.wear_pct_per_lap
        if a.wear_pct_per_lap is not None and b.wear_pct_per_lap is not None
        else None
    )

    warnings: list[str] = []
    incomparable = False
    need = MIN_LAPS.get(mode, 2)
    if a.n_laps < need or b.n_laps < need:
        warnings.append(f"Too few laps for a {mode} verdict (need ≥{need} per run, got {a.n_laps} vs {b.n_laps}).")
        incomparable = True
    if a.conditions_state != b.conditions_state:
        warnings.append(f"Different track state ({a.conditions_state} vs {b.conditions_state}).")
        incomparable = True
    if a.compound != b.compound:
        warnings.append(f"Different tyre compound ({a.compound} vs {b.compound}) — pace is not comparable.")
        incomparable = True
    if a.fuel_kg is not None and b.fuel_kg is not None and abs(a.fuel_kg - b.fuel_kg) > FUEL_WARN_KG:
        warnings.append(f"Fuel differs by {abs(a.fuel_kg - b.fuel_kg):.0f} kg — correction is only approximate.")
    if a.session_type == "FP1":
        warnings.append("Earlier run was FP1 (green track): part of the gain is track evolution, not setup.")

    if incomparable:
        verdict, reason = "inconclusive", "Runs are not directly comparable."
    elif pace_delta <= -noise:
        verdict, reason = "better", f"{pace_delta:+.3f}s (beyond ±{noise:.2f}s noise)"
    elif pace_delta >= noise:
        verdict, reason = "worse", f"{pace_delta:+.3f}s (beyond ±{noise:.2f}s noise)"
    elif fixed:
        verdict, reason = "better", f"pace within noise ({pace_delta:+.3f}s) but the balance symptom shrank"
    elif worse:
        verdict, reason = "worse", f"pace within noise ({pace_delta:+.3f}s) but the balance symptom grew"
    else:
        verdict, reason = "neutral", f"{pace_delta:+.3f}s is inside ±{noise:.2f}s noise"

    return RunComparison(
        mode=mode,
        session_a_id=a.session_id,
        session_b_id=b.session_id,
        run_a=a,
        run_b=b,
        setup_diff=diff_setups(mech_setup(a.setup), mech_setup(b.setup)),
        pace_delta=float(pace_delta),
        noise=float(noise),
        deg_delta=deg_delta,
        balance_delta=balance_delta,
        symptom_phases=phases,
        symptom_delta=sym_delta,
        symptom_fixed=fixed,
        symptom_worse=worse,
        temp_delta=temp_delta,
        lockup_delta=lockup_delta,
        wear_delta=wear_delta,
        corner_deltas=corner_deltas or [],
        verdict=verdict,
        verdict_reason=reason,
        warnings=warnings,
    )


@lru_cache(maxsize=64)
def _cached_runs(app_root: str, session_id: int) -> tuple[Run, ...]:
    root = Path(app_root) if app_root else None
    session = get_session(session_id, root)
    if not session:
        return ()
    df = load_session_telemetry(session_id, root, columns=ANALYSIS_COLUMNS)
    return tuple(split_runs(df, session=session, track_length=session.get("track_length")))


def load_session_runs(session_id: int, app_root: Path | None = None) -> list[Run]:
    """Runs of a stored session (cached — stored sessions never change after import)."""
    return list(_cached_runs(str(app_root) if app_root else "", int(session_id)))


def clear_run_cache() -> None:
    _cached_runs.cache_clear()


def compare_sessions_runs(
    session_a_id: int,
    session_b_id: int,
    mode: str,
    app_root: Path | None = None,
    *,
    with_corners: bool = True,
) -> RunComparison | None:
    """Best `mode` run of session A vs best `mode` run of session B; None if either has none."""
    run_a = best_run(load_session_runs(session_a_id, app_root), mode)
    run_b = best_run(load_session_runs(session_b_id, app_root), mode)
    if run_a is None or run_b is None:
        return None
    sess_a, sess_b = get_session(session_a_id, app_root), get_session(session_b_id, app_root)
    corners: list[dict[str, Any]] = []
    if with_corners and sess_a and sess_b:
        try:
            track = normalize_track_name(sess_b.get("track") or sess_a.get("track"))
            length = sess_b.get("track_length") or sess_a.get("track_length")
            corners = _corner_deltas(
                load_session_telemetry(session_a_id, app_root, columns=ANALYSIS_COLUMNS),
                load_session_telemetry(session_b_id, app_root, columns=ANALYSIS_COLUMNS),
                run_a,
                run_b,
                track,
                float(length) if length else None,
            )
        except Exception:  # corner data is a nice-to-have; never block the verdict
            corners = []
    return compare_runs(run_a, run_b, mode=mode, session_a=sess_a, session_b=sess_b, corner_deltas=corners)


def sessions_on_track(track: str, app_root: Path | None = None) -> pd.DataFrame:
    """Sessions on a track, oldest first (created_at, then id)."""
    sessions = list_track_sessions(track, app_root)
    if sessions.empty:
        return sessions
    return sessions.sort_values(["created_at", "id"], ascending=True).reset_index(drop=True)


def previous_comparable(
    track: str,
    session_id: int,
    mode: str,
    app_root: Path | None = None,
) -> dict[str, Any] | None:
    """Newest earlier session on the track in the same track state that has a `mode` run."""
    sessions = sessions_on_track(track, app_root)
    if sessions.empty or int(session_id) not in sessions["id"].astype(int).values:
        return None
    pos = int(np.flatnonzero(sessions["id"].astype(int).values == int(session_id))[0])
    target = get_session(int(session_id), app_root) or {}
    from .conditions import _as_state

    state = _as_state(target.get("conditions"))
    for i in range(pos - 1, -1, -1):
        row = sessions.iloc[i]
        if _as_state(row.get("conditions")) != state:
            continue
        if best_run(load_session_runs(int(row["id"]), app_root), mode) is not None:
            return dict(row)
    return None
