"""Recommendation journal + measured experiments: did the advised garage change help?"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .conditions import _as_state
from .corners import normalize_track_name
from .db import connect
from .runs import Run, best_run
from .setup_eval import (
    MIN_LAPS,
    RunComparison,
    compare_sessions_runs,
    load_session_runs,
    previous_comparable,
    sessions_on_track,
)

LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS setup_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    track TEXT NOT NULL,
    session_id INTEGER NOT NULL,
    variant TEXT NOT NULL,
    conditions_state TEXT,
    base_setup_json TEXT,
    proposed_setup_json TEXT,
    changes_json TEXT,
    diagnosis_json TEXT,
    status TEXT DEFAULT 'pending',
    followup_session_id INTEGER,
    applied_frac REAL,
    UNIQUE(session_id, variant)
);

CREATE TABLE IF NOT EXISTS setup_experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track TEXT NOT NULL,
    from_session_id INTEGER NOT NULL,
    to_session_id INTEGER NOT NULL,
    mode TEXT NOT NULL,
    conditions_state TEXT,
    changes_json TEXT,
    recommendation_id INTEGER,
    source TEXT,
    pace_delta REAL,
    noise REAL,
    balance_delta_json TEXT,
    symptom_json TEXT,
    verdict TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(from_session_id, to_session_id, mode)
);

CREATE TABLE IF NOT EXISTS setup_eval_state (
    track TEXT PRIMARY KEY,
    signature TEXT NOT NULL,
    evaluated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_setup_exp_track ON setup_experiments(track, to_session_id);
"""

# A recommended change counts as applied once the garage moved this share of the advised delta.
APPLIED_SHARE = 0.5
# Experiments with more mechanical changes than this say too little about any single lever.
MAX_ATTRIBUTABLE_CHANGES = 3
GLOBAL_WEIGHT = 0.5
# Keys that mirror another channel or are not a car change.
_IGNORED_KEYS = frozenset({"fuel_setup", "front_brake_bias", "tyre_compound"})


def ensure_log_schema(app_root: Path | None = None) -> None:
    with connect(app_root) as conn:
        conn.executescript(LOG_SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _json_default(o: Any) -> Any:
    """numpy scalars (np.int64 etc.) are not JSON serialisable by default."""
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def _direction(delta: float) -> int:
    return 1 if delta > 0 else -1


# --------------------------------------------------------------------------- recommendations


def save_recommendation(
    *,
    session_id: int,
    track: str,
    variant: str,
    conditions: str | None,
    base_setup: dict[str, Any] | None,
    proposed_setup: dict[str, Any] | None,
    changes: list[Any],
    diagnosis: dict[str, Any] | None = None,
    app_root: Path | None = None,
) -> int:
    """Upsert the builder's advice for (session, variant); a re-build resets the follow-up."""
    ensure_log_schema(app_root)
    track_n = normalize_track_name(track) or track
    mech = []
    for c in changes:
        key = c.key if hasattr(c, "key") else c["key"]
        if key in _IGNORED_KEYS:
            continue
        mech.append(
            {
                "key": key,
                "label": getattr(c, "label", None) or (c.get("label") if isinstance(c, dict) else key),
                "before": float(c.before if hasattr(c, "before") else c["before"]),
                "after": float(c.after if hasattr(c, "after") else c["after"]),
                "reason": getattr(c, "reason", None) or (c.get("reason") if isinstance(c, dict) else ""),
            }
        )
    with connect(app_root) as conn:
        conn.execute(
            """
            INSERT INTO setup_recommendations
                (created_at, track, session_id, variant, conditions_state, base_setup_json,
                 proposed_setup_json, changes_json, diagnosis_json, status, followup_session_id, applied_frac)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL)
            ON CONFLICT(session_id, variant) DO UPDATE SET
                created_at = excluded.created_at,
                track = excluded.track,
                conditions_state = excluded.conditions_state,
                base_setup_json = excluded.base_setup_json,
                proposed_setup_json = excluded.proposed_setup_json,
                changes_json = excluded.changes_json,
                diagnosis_json = excluded.diagnosis_json,
                status = 'pending',
                followup_session_id = NULL,
                applied_frac = NULL
            """,
            (
                _now(),
                track_n,
                int(session_id),
                variant.lower(),
                _as_state(conditions),
                json.dumps(base_setup or {}, default=_json_default),
                json.dumps(proposed_setup or {}, default=_json_default),
                json.dumps(mech, default=_json_default),
                json.dumps(diagnosis or {}, default=_json_default),
            ),
        )
        row = conn.execute(
            "SELECT id FROM setup_recommendations WHERE session_id = ? AND variant = ?",
            (int(session_id), variant.lower()),
        ).fetchone()
    return int(row["id"])


def _rec_row(row: Any) -> dict[str, Any]:
    out = dict(row)
    out["changes"] = _loads(out.get("changes_json"), [])
    out["diagnosis"] = _loads(out.get("diagnosis_json"), {})
    return out


def get_recommendations(
    app_root: Path | None = None,
    *,
    session_id: int | None = None,
    track: str | None = None,
) -> list[dict[str, Any]]:
    ensure_log_schema(app_root)
    clauses, params = [], []
    if session_id is not None:
        clauses.append("session_id = ?")
        params.append(int(session_id))
    if track:
        clauses.append("track = ?")
        params.append(normalize_track_name(track) or track)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(app_root) as conn:
        rows = conn.execute(
            f"SELECT * FROM setup_recommendations {where} ORDER BY created_at DESC", params
        ).fetchall()
    return [_rec_row(r) for r in rows]


@dataclass
class Application:
    applied: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    opposite: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)  # changed by hand, never advised
    frac: float | None = None

    @property
    def status(self) -> str:
        if self.frac is None:
            return "pending"
        if self.frac >= 0.75:
            return "applied"
        return "partial" if self.applied else "ignored"


def match_application(
    changes: list[dict[str, Any]],
    new_setup: dict[str, Any],
    old_setup: dict[str, Any] | None = None,
) -> Application:
    """
    Did the next session's garage follow the advice?

    A change is applied when the value moved >=50% of the advised delta from the advised
    `before` toward `after`. `old_setup` (the garage the advice was built on) is only used to
    spot extra manual changes the builder never suggested.
    """
    app = Application()
    advised = {c["key"] for c in changes}
    for c in changes:
        key = c["key"]
        target = float(c["after"]) - float(c["before"])
        if key not in new_setup or abs(target) < 1e-9:
            app.missed.append(key)
            continue
        moved = float(new_setup[key]) - float(c["before"])
        if moved * target < 0:
            app.opposite.append(key)
        elif abs(moved) >= APPLIED_SHARE * abs(target):
            app.applied.append(key)
        else:
            app.missed.append(key)
    if old_setup:
        for key, old_v in old_setup.items():
            if key in advised or key in _IGNORED_KEYS or key not in new_setup:
                continue
            if abs(float(new_setup[key]) - float(old_v)) > 1e-6:
                app.extra.append(key)
    if changes:
        app.frac = len(app.applied) / len(changes)
    return app


# --------------------------------------------------------------------------- evaluation


def _update_rec(app_root: Path | None, rec_id: int, app: Application, followup_session_id: int) -> None:
    with connect(app_root) as conn:
        conn.execute(
            "UPDATE setup_recommendations SET status = ?, followup_session_id = ?, applied_frac = ? WHERE id = ?",
            (app.status, int(followup_session_id), app.frac, int(rec_id)),
        )


def _upsert_experiment(app_root: Path | None, track: str, comp: RunComparison, rec: dict[str, Any] | None, source: str) -> None:
    run_a = comp.run_a
    symptom = {
        "issue": run_a.balance.get("issue"),
        "phase": run_a.balance.get("issue_phase"),
        "strength": run_a.balance.get("issue_strength"),
        "phases": comp.symptom_phases,
        "delta": comp.symptom_delta,
        "fixed": comp.symptom_fixed,
        "worse": comp.symptom_worse,
    }
    with connect(app_root) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO setup_experiments
                (track, from_session_id, to_session_id, mode, conditions_state, changes_json,
                 recommendation_id, source, pace_delta, noise, balance_delta_json, symptom_json,
                 verdict, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track,
                int(comp.session_a_id),
                int(comp.session_b_id),
                comp.mode,
                comp.run_b.conditions_state,
                json.dumps(comp.setup_diff),
                int(rec["id"]) if rec else None,
                source,
                comp.pace_delta,
                comp.noise,
                json.dumps(comp.balance_delta),
                json.dumps(symptom),
                comp.verdict,
                _now(),
            ),
        )


def _followup_setup(runs: list[Run], variant: str) -> dict[str, float] | None:
    run = best_run(runs, variant) or (runs[0] if runs else None)
    return dict(run.setup) if run else None


def _signature(sessions_df: Any) -> str:
    return ",".join(str(int(i)) for i in sessions_df["id"].tolist())


def evaluate_track(track: str, app_root: Path | None = None, *, force: bool = False) -> dict[str, int]:
    """
    (Re)build the follow-up status of recommendations and the experiments on one track.

    Idempotent: recommendations are matched to the very next session, experiments are keyed by
    (from, to, mode). Skipped when nothing new happened since the last evaluation.
    """
    ensure_log_schema(app_root)
    track_n = normalize_track_name(track) or track
    sessions = sessions_on_track(track_n, app_root)
    stats = {"recommendations": 0, "experiments": 0, "skipped": 0}
    if sessions.empty:
        return stats

    sig = _signature(sessions)
    with connect(app_root) as conn:
        state = conn.execute("SELECT signature FROM setup_eval_state WHERE track = ?", (track_n,)).fetchone()
        pending = conn.execute(
            "SELECT COUNT(*) AS n FROM setup_recommendations WHERE track = ? AND status = 'pending'", (track_n,)
        ).fetchone()["n"]
    if not force and state and state["signature"] == sig and not pending:
        stats["skipped"] = 1
        return stats

    ids = [int(i) for i in sessions["id"].tolist()]
    # 1) recommendations -> next session
    for pos in range(len(ids) - 1):
        a_id, b_id = ids[pos], ids[pos + 1]
        for rec in get_recommendations(app_root, session_id=a_id):
            b_runs = load_session_runs(b_id, app_root)
            new_setup = _followup_setup(b_runs, rec["variant"])
            if new_setup is None:
                continue
            old_setup = _loads(rec.get("base_setup_json"), {})
            app = match_application(rec["changes"], new_setup, old_setup)
            _update_rec(app_root, rec["id"], app, b_id)
            stats["recommendations"] += 1

    # 2) experiments: every session vs the previous comparable one, per mode
    for b_id in ids[1:]:
        for mode in ("quali", "race"):
            prev = previous_comparable(track_n, b_id, mode, app_root)
            if prev is None:
                continue
            comp = compare_sessions_runs(int(prev["id"]), b_id, mode, app_root)
            if comp is None or not comp.setup_diff:
                continue
            rec = next(
                (r for r in get_recommendations(app_root, session_id=int(prev["id"])) if r["variant"] == mode),
                None,
            )
            source = "manual"
            if rec:
                app = match_application(rec["changes"], comp.run_b.setup, comp.run_a.setup)
                if app.applied and app.extra:
                    source = "mixed"
                elif app.applied:
                    source = "recommended"
            _upsert_experiment(app_root, track_n, comp, rec, source)
            stats["experiments"] += 1

    with connect(app_root) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO setup_eval_state (track, signature, evaluated_at) VALUES (?, ?, ?)",
            (track_n, sig, _now()),
        )
    return stats


def evaluate_all(app_root: Path | None = None, *, force: bool = False) -> dict[str, dict[str, int]]:
    from .db import list_tracks

    out = {}
    for track in list_tracks(app_root):
        try:
            out[track] = evaluate_track(track, app_root, force=force)
        except Exception as exc:  # one broken export must not block startup
            out[track] = {"error": str(exc)}  # type: ignore[dict-item]
    return out


def followup_entries(session_id: int, app_root: Path | None = None) -> list[dict[str, Any]]:
    """
    Earlier advice that this session is the follow-up for, with what was applied and what it did.

    Each entry: rec, application (Application), experiment (dict | None), symptom (str).
    """
    entries = []
    runs = load_session_runs(int(session_id), app_root)
    for rec in get_recommendations(app_root):
        if rec.get("followup_session_id") != int(session_id):
            continue
        run = best_run(runs, rec["variant"]) or (runs[0] if runs else None)
        app = match_application(rec["changes"], run.setup, None) if run else Application()
        exp = next(
            (
                e
                for e in list_experiments(rec["track"], app_root, mode=rec["variant"])
                if e["from_session_id"] == rec["session_id"] and e["to_session_id"] == int(session_id)
            ),
            None,
        )
        diag = rec.get("diagnosis") or {}
        issue = diag.get("issue")
        symptom = f"{issue} ({diag.get('phase')})" if issue and issue != "balanced" else "balance"
        entries.append({"rec": rec, "application": app, "experiment": exp, "symptom": symptom})
    return entries


def list_experiments(track: str, app_root: Path | None = None, *, mode: str | None = None) -> list[dict[str, Any]]:
    ensure_log_schema(app_root)
    track_n = normalize_track_name(track) or track
    sql = "SELECT * FROM setup_experiments WHERE track = ?"
    params: list[Any] = [track_n]
    if mode:
        sql += " AND mode = ?"
        params.append(mode)
    sql += " ORDER BY to_session_id DESC"
    with connect(app_root) as conn:
        rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["changes"] = _loads(d.get("changes_json"), [])
        d["symptom"] = _loads(d.get("symptom_json"), {})
        d["balance_delta"] = _loads(d.get("balance_delta_json"), {})
        out.append(d)
    return out


# --------------------------------------------------------------------------- learning


@dataclass
class LeverStat:
    helped: float = 0.0
    hurt: float = 0.0
    hurt_clear: float = 0.0  # worse by >= 2x noise
    neutral: float = 0.0
    pace_sum: float = 0.0
    weight_sum: float = 0.0
    symptom_fixed: float = 0.0
    last_hurt: tuple[int, int] | None = None  # (from_session, to_session) of the latest bad experiment
    last_helped: tuple[int, int] | None = None
    last_delta: float | None = None  # size of the most recent move that helped

    @property
    def mean_pace(self) -> float | None:
        return self.pace_sum / self.weight_sum if self.weight_sum else None


def _matches_symptom(sym: dict[str, Any], issue: str | None, phase: str | None) -> bool:
    if not issue or sym.get("issue") != issue:
        return False
    p_exp, p_now = str(sym.get("phase") or "all"), str(phase or "all")
    return "all" in (p_exp, p_now) or p_exp == p_now


def lever_stats(
    track: str,
    issue: str | None,
    phase: str | None,
    app_root: Path | None = None,
) -> dict[tuple[str, int], LeverStat]:
    """
    What happened when this lever moved this way against the same symptom.

    This track counts fully, other tracks at half weight. Experiments with many simultaneous
    changes contribute only to the pace mean (shared 1/n), never to helped/hurt counts.
    """
    ensure_log_schema(app_root)
    track_n = normalize_track_name(track) or track
    with connect(app_root) as conn:
        rows = conn.execute("SELECT * FROM setup_experiments ORDER BY to_session_id ASC").fetchall()
    stats: dict[tuple[str, int], LeverStat] = {}
    for r in rows:
        verdict = r["verdict"]
        if verdict == "inconclusive":
            continue
        sym = _loads(r["symptom_json"], {})
        if not _matches_symptom(sym, issue, phase):
            continue
        changes = [c for c in _loads(r["changes_json"], []) if c.get("delta") is not None and c["key"] not in _IGNORED_KEYS]
        if not changes:
            continue
        weight = 1.0 if r["track"] == track_n else GLOBAL_WEIGHT
        share = 1.0 / len(changes)
        clear = r["pace_delta"] is not None and r["noise"] and float(r["pace_delta"]) >= 2 * float(r["noise"])
        for c in changes:
            st = stats.setdefault((c["key"], _direction(float(c["delta"]))), LeverStat())
            if r["pace_delta"] is not None:
                st.pace_sum += float(r["pace_delta"]) * share * weight
                st.weight_sum += share * weight
            if len(changes) > MAX_ATTRIBUTABLE_CHANGES:
                continue
            pair = (int(r["from_session_id"]), int(r["to_session_id"]))
            if verdict == "worse":
                st.hurt += weight
                if clear:
                    st.hurt_clear += weight
                st.last_hurt = pair
            elif verdict == "better":
                st.helped += weight
                st.last_helped = pair
                st.last_delta = float(c["delta"])
                if sym.get("fixed"):
                    st.symptom_fixed += weight
            else:
                st.neutral += weight
    return stats


@dataclass
class SetupHistory:
    track: str
    mode: str
    state: str
    last_experiment: dict[str, Any] | None = None
    pending_rec: dict[str, Any] | None = None
    levers: dict[tuple[str, int], LeverStat] = field(default_factory=dict)
    best_verified: dict[str, Any] | None = None  # {setup, session_id, pace, compound, laps}
    n_experiments: int = 0

    def should_avoid(self, key: str, direction: int) -> LeverStat | None:
        """Lever stat if this key/direction hurt repeatedly (or once, clearly) for the same symptom."""
        st = self.levers.get((key, direction))
        if st and (st.hurt >= 2.0 or st.hurt_clear >= 1.0) and st.hurt > st.helped:
            return st
        return None

    def worked(self, key: str, direction: int) -> LeverStat | None:
        st = self.levers.get((key, direction))
        if st and st.helped >= 1.0 and st.helped > st.hurt:
            return st
        return None


def best_verified_setup(
    track: str,
    mode: str,
    state: str,
    app_root: Path | None = None,
    *,
    compound: int | None = None,
) -> dict[str, Any] | None:
    """Mechanical setup of the fastest run (enough laps, same track state, same compound) on the track."""
    best: tuple[float, Run, int] | None = None
    sessions = sessions_on_track(track, app_root)
    for _, row in sessions.iterrows():
        if _as_state(row.get("conditions")) != state:
            continue
        for run in load_session_runs(int(row["id"]), app_root):
            if run.kind != mode or run.n_laps < MIN_LAPS[mode]:
                continue
            if compound is not None and run.compound != compound:
                continue
            pace = run.best_corrected if mode == "quali" else run.median_corrected
            if best is None or pace < best[0]:
                best = (pace, run, int(row["id"]))
    if best is None:
        return None
    pace, run, sid = best
    return {"setup": dict(run.setup), "session_id": sid, "pace": float(pace), "compound": run.compound, "laps": run.n_laps}


def load_history(
    track: str,
    mode: str,
    state: str = "dry",
    *,
    issue: str | None = None,
    phase: str | None = None,
    compound: int | None = None,
    app_root: Path | None = None,
    before_session_id: int | None = None,
) -> SetupHistory:
    """Everything the builder needs to learn from earlier sessions on this track."""
    track_n = normalize_track_name(track) or track
    mode = mode.lower()
    experiments = [
        e
        for e in list_experiments(track_n, app_root, mode=mode)
        if e["conditions_state"] == state and (before_session_id is None or e["to_session_id"] <= before_session_id)
    ]
    recs = [
        r
        for r in get_recommendations(app_root, track=track_n)
        if r["variant"] == mode and (before_session_id is None or r["session_id"] < before_session_id)
    ]
    return SetupHistory(
        track=track_n,
        mode=mode,
        state=state,
        last_experiment=experiments[0] if experiments else None,
        pending_rec=recs[0] if recs else None,
        levers=lever_stats(track_n, issue, phase, app_root),
        best_verified=best_verified_setup(track_n, mode, state, app_root, compound=compound),
        n_experiments=len(experiments),
    )
