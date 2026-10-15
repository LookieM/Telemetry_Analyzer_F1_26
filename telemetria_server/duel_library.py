"""
Offline setup duel: the setups driven on a track in the library, and a ranking of 2-3 of them on comparable runs.

Candidates come from the run splitter over every session of the track (grouped by the mechanical fingerprint).
Runs are only compared inside one (conditions state, compound) group that every contestant has with at least
``MIN_CLEAN_LAPS`` clean laps; otherwise the result says why the setups are not comparable.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from telemetry import corner_store, duel_store, strategy, tyres
from telemetry.compounds import c_label, softness
from telemetry.corner_balance import BALANCE_COLUMNS, PHASES, lap_balance, session_balance
from telemetry.corners import normalize_track_name
from telemetry.db import load_session_telemetry
from telemetry.metrics import FUEL_S_PER_KG, fuel_corrected_time, get_lap
from telemetry.setup_eval import load_session_runs

from .duel_ranking import Contestant, rank_contestants
from .live.lap_correction import Lap, correct_groups, representative_laps

MIN_CLEAN_LAPS = 3
BALANCE_MAX_LAPS = 8
WEAR_MIN_POINTS = 3


@dataclass
class RunLaps:
    """One library run reduced to what the duel needs: its clean laps and tyre wear rate."""

    fingerprint: str
    session_id: int
    session_type: str
    created_at: str
    run_idx: int
    compound: int | None
    state: str
    kind: str
    fuel_kg: float | None
    first_lap: int
    last_lap: int
    n_laps: int
    clean: list[Lap] = field(default_factory=list)
    wear_pct_per_lap: float | None = None

    @property
    def group(self) -> tuple[str, int | None]:
        return (self.state, self.compound)


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _wear_slope(laps: list[int], wear: list[float | None]) -> float | None:
    pts = [(x, w) for x, w in zip(laps, wear) if w is not None and w >= 0]
    if len(pts) < WEAR_MIN_POINTS:
        return None
    slope = float(np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)[0])
    return slope if slope > 0 else None


@lru_cache(maxsize=256)
def _session_run_laps(app_root: str, session_id: int) -> tuple[RunLaps, ...]:
    root = Path(app_root) if app_root else None
    session, summary = tyres.session_summary(session_id, root)
    if not session or summary.empty:
        return ()
    stints = tyres.tyre_stints(summary)
    age: dict[int, int] = {}
    stint_of: dict[int, int] = {}
    for st in stints:
        for lap in st.laps:
            age[lap] = st.ages.get(lap, 0)
            stint_of[lap] = st.idx
    rows = {int(r["lap"]): r for _, r in summary.iterrows()}
    out: list[RunLaps] = []
    for run in load_session_runs(session_id, root):
        if not run.mech_fp:
            continue
        clean: list[Lap] = []
        wear: list[float | None] = []
        for lap in run.laps:
            r = rows.get(lap)
            if r is None:
                continue
            wear.append(_num(r.get("tyre_wear_avg")))
            t = _num(r.get("lap_time"))
            if r.get("lap_class") != "push" or t is None or t <= 0:
                continue
            clean.append(Lap(
                lap=lap, lap_time_s=t, fuel_start=_num(r.get("fuel_start")), fuel_end=_num(r.get("fuel_end")),
                compound=run.compound, tyre_set_idx=stint_of.get(lap), tyre_age_laps=age.get(lap, 0),
            ))
        out.append(RunLaps(
            fingerprint=run.mech_fp, session_id=session_id, session_type=run.session_type, created_at=str(session.get("created_at") or ""),
            run_idx=run.idx, compound=run.compound, state=run.conditions_state, kind=run.kind, fuel_kg=run.fuel_kg,
            first_lap=run.laps[0], last_lap=run.laps[-1], n_laps=run.n_laps, clean=clean,
            wear_pct_per_lap=run.wear_pct_per_lap if run.wear_pct_per_lap is not None else _wear_slope(run.laps, wear),
        ))
    return tuple(out)


def clear_cache() -> None:
    _session_run_laps.cache_clear()


def collect_candidates(track: str, root: Path) -> dict[str, list[RunLaps]]:
    """mechanical fingerprint -> runs on the track (all sessions whose normalised track name matches)."""
    out: dict[str, list[RunLaps]] = {}
    for s in corner_store.track_sessions(track, root):
        try:
            runs = _session_run_laps(str(root), int(s["id"]))
        except FileNotFoundError:
            continue
        for run in runs:
            out.setdefault(run.fingerprint, []).append(run)
    return out


def _median_pace(laps: list[Lap]) -> float | None:
    reps = representative_laps(laps)
    if not reps:
        return None
    return float(np.median([fuel_corrected_time(x.lap_time_s, x.fuel_mid) for x in reps]))


def setups_payload(track: str, root: Path) -> dict[str, Any]:
    names = duel_store.get_names(track, root)
    setups = []
    for fp, runs in collect_candidates(track, root).items():
        runs = sorted(runs, key=lambda r: (r.created_at, r.run_idx), reverse=True)
        run_rows = []
        for r in runs:
            reps = representative_laps(r.clean)
            best = min((x.lap_time_s for x in reps), default=None)
            run_rows.append({
                "session_id": r.session_id, "session_type": r.session_type, "run": r.run_idx + 1,
                "first_lap": r.first_lap, "last_lap": r.last_lap, "n_laps": r.n_laps, "n_clean": len(reps),
                "compound": r.compound, "compound_label": c_label(r.compound), "state": r.state, "kind": r.kind,
                "fuel_kg": r.fuel_kg, "pace_s": _median_pace(r.clean), "best_s": best, "wear_pct_per_lap": r.wear_pct_per_lap,
            })
        setups.append({
            "fingerprint": fp, "name": names.get(fp),
            "n_runs": len(runs), "n_clean": sum(x["n_clean"] for x in run_rows),
            "sessions": sorted({r.session_id for r in runs}), "last_driven": runs[0].created_at,
            "runs": run_rows,
        })
    setups.sort(key=lambda s: s["last_driven"], reverse=True)
    return {"track": track, "setups": setups}


# --------------------------------------------------------------------------- wear cost from the strategy model


def wear_plan_time(track: str, state: str, compound: int | None, root: Path):
    """(plan_time, race_laps, deg_table): plan_time(wear_pct_per_lap) = best race time on a stint plan that uses
    only the duel's compound, with its wear rate (and degradation, scaled with it) replaced. None when the track has
    no usable tyre model."""
    try:
        model = tyres.track_compound_model(track, state, root, wear_limit=tyres.default_wear_limit(tyres.library_race_stats(root)))
    except Exception:
        return None, None, None
    if not model.compounds or compound is None:
        return None, None, None
    deg_table = {c: m.deg_s_per_lap for c, m in model.compounds.items()}
    specs = strategy.specs_from_model(model)
    base = next((s for s in specs if s.code == compound), None) or min(specs, key=lambda s: abs(softness(s.code) - softness(compound)))
    if not base.wear_pct_per_lap or base.wear_pct_per_lap <= 1e-6:
        return None, None, deg_table
    params = replace(strategy.default_params(model, track), require_two_compounds=False)
    base = replace(base, use=True)

    def plan_time(wear: float) -> float | None:
        scale = float(np.clip(wear / base.wear_pct_per_lap, 0.3, 3.0))
        spec = replace(base, wear_pct_per_lap=wear, deg_s_per_lap=base.deg_s_per_lap * scale)
        plans = strategy.optimise([spec], params)
        return plans[0].race_time if plans else None

    return plan_time, params.laps, deg_table


# --------------------------------------------------------------------------- balance


def _balance(track: str, root: Path, laps_by_session: dict[int, list[int]]) -> tuple[dict[str, float | None] | None, str | None]:
    """Raw understeer index per phase (median over corners and laps) and a reason when it is not available."""
    try:
        corners = corner_store.ensure_track_corners(track, root)["corners"]
    except corner_store.NoCleanLap as exc:
        return None, str(exc)
    per_lap: list[dict[str, Any]] = []
    for sid, laps in laps_by_session.items():
        try:
            df = load_session_telemetry(sid, root, columns=[*corner_store.FRAME_COLUMNS, *BALANCE_COLUMNS])
        except FileNotFoundError:
            continue
        for n in laps:
            b = lap_balance(get_lap(df, n), corners)
            per_lap.append({**b, "lap": n})
            if not b["available"]:
                return None, b["reason"]
    res = session_balance(per_lap, corners)
    if not res["available"]:
        return None, res["reason"]
    out: dict[str, float | None] = {}
    for p in PHASES:
        vals = [c[p] for c in res["corners"] if c[p] is not None]
        out[p] = float(np.median(vals)) if vals else None
    return out, None


# --------------------------------------------------------------------------- the duel


def by_session_all(runs: list[RunLaps], laps: list[Lap]) -> dict[int, list[Lap]]:
    """The counted laps grouped by the session they were driven in."""
    out: dict[int, list[Lap]] = {}
    for r in runs:
        mine = [x for x in laps if any(x is y for y in r.clean)]
        if mine:
            out.setdefault(r.session_id, []).extend(mine)
    return out


def _label(fp: str, names: dict[str, str]) -> str:
    return names.get(fp) or f"Setup {fp[:6]}"


def _group_text(group: tuple[str, int | None]) -> str:
    return f"{c_label(group[1])} {group[0]}"


def run_duel(track: str, fingerprints: list[str], root: Path, *, persist: bool = True) -> dict[str, Any]:
    """Rank the given setups of a track on comparable library runs. Raises KeyError for an unknown fingerprint."""
    cands = collect_candidates(track, root)
    for fp in fingerprints:
        if fp not in cands:
            raise KeyError(fp)
    names = duel_store.get_names(track, root)
    labels = {fp: _label(fp, names) for fp in fingerprints}

    # Clean laps per fingerprint and (state, compound) group, after the mistake filter.
    groups: dict[str, dict[tuple[str, int | None], list[RunLaps]]] = {}
    counts: dict[str, dict[tuple[str, int | None], int]] = {}
    for fp in fingerprints:
        groups[fp] = {}
        for r in cands[fp]:
            groups[fp].setdefault(r.group, []).append(r)
        counts[fp] = {g: len(representative_laps([x for r in rs for x in r.clean])) for g, rs in groups[fp].items()}
    usable = {fp: {g for g, n in c.items() if n >= MIN_CLEAN_LAPS} for fp, c in counts.items()}

    def describe(fp: str) -> str:
        have = ", ".join(f"{_group_text(g)} ({n} clean laps)" for g, n in sorted(counts[fp].items(), key=lambda kv: -kv[1]))
        return f"{labels[fp]} has {have or 'no clean laps'}"

    pairs = []
    for i, a in enumerate(fingerprints):
        for b in fingerprints[i + 1:]:
            reason = None
            if not usable[a] or not usable[b]:
                short = [labels[x] for x in (a, b) if not usable[x]]
                reason = f"{' and '.join(short)} {'has' if len(short) == 1 else 'have'} no run with at least {MIN_CLEAN_LAPS} clean laps in one condition and compound"
            elif not (usable[a] & usable[b]):
                reason = f"No shared condition and compound with {MIN_CLEAN_LAPS}+ clean laps each: {describe(a)}; {describe(b)}"
            pairs.append({"a": a, "b": b, "comparable": reason is None, "reason": reason})

    common = set.intersection(*usable.values()) if usable else set()
    out: dict[str, Any] = {
        "track": track, "mode": "offline", "fingerprints": fingerprints, "names": labels,
        "pairs": pairs, "comparable": bool(common), "reasons": [], "condition": None, "ranking": None,
        "min_clean_laps": MIN_CLEAN_LAPS,
    }
    if not common:
        out["reasons"] = [p["reason"] for p in pairs if p["reason"]]
        if all(p["comparable"] for p in pairs):  # three setups, every pair shares something but not all three
            out["reasons"] = ["No single condition and compound has " f"{MIN_CLEAN_LAPS}+ clean laps for all of: " + "; ".join(describe(fp) for fp in fingerprints)]
    else:
        # The group with the most laps for the least-driven contestant, dry first.
        group = max(common, key=lambda g: (min(counts[fp][g] for fp in fingerprints), g[0] == "dry", sum(counts[fp][g] for fp in fingerprints)))
        state, compound = group
        plan_time, race_laps, deg_table = wear_plan_time(track, state, compound, root)
        laps = {fp: representative_laps([x for r in groups[fp][group] for x in r.clean]) for fp in fingerprints}
        corrected = correct_groups(laps, FUEL_S_PER_KG, deg_table)
        contestants = []
        balance_reason = None
        for fp in fingerprints:
            runs = groups[fp][group]
            wears = [(r.wear_pct_per_lap, len(r.clean)) for r in runs if r.wear_pct_per_lap is not None]
            wear = float(np.average([w for w, _ in wears], weights=[n for _, n in wears])) if wears else None
            fastest = sorted(zip(corrected.times[fp], laps[fp]), key=lambda t: t[0])[:BALANCE_MAX_LAPS]
            by_session: dict[int, list[int]] = {}
            for _, lap in fastest:
                sid = next(r.session_id for r in runs if any(x is lap for x in r.clean))
                by_session.setdefault(sid, []).append(lap.lap)
            bal, reason = _balance(track, root, by_session)
            balance_reason = balance_reason or reason
            contestants.append(Contestant(
                key=fp, name=labels[fp], times=corrected.times[fp], wear_pct_per_lap=wear, balance=bal,
                sessions=sorted({sid for sid, ls in by_session_all(runs, laps[fp]).items() if ls}),
                extra={"fingerprint": fp, "sessions": sorted({r.session_id for r in runs}), "runs": len(runs)},
            ))
        out["condition"] = {"state": state, "compound": compound, "compound_label": c_label(compound)}
        out["correction"] = {"deg_s_per_lap": corrected.deg_s_per_lap, "deg_source": corrected.deg_source, "fuel_s_per_kg": FUEL_S_PER_KG}
        out["balance_note"] = balance_reason
        out["ranking"] = rank_contestants(contestants, plan_time=plan_time, race_laps=race_laps)
    if persist:
        out["duel_id"] = duel_store.save_duel(track, "offline", out, root)
    return out


def track_name(track: str) -> str:
    return normalize_track_name(track) or track

