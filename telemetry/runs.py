"""Split a session into runs (stints on one garage setup + tyre set) with fuel-corrected pace."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .balance import analyze_practice_balance
from .compounds import c_label
from .conditions import _as_state
from .loader import has_telemetry_setup, resolve_session_setup
from .metrics import build_lap_summary, fuel_corrected_time
from .setup_history import mech_fingerprint, parse_setup_json

# A run is a "race" run when it carries real fuel or is long enough to show degradation.
RACE_FUEL_KG = 15.0
RACE_MIN_LAPS = 5
# Fuel jumps up by more than this between laps => pit stop / new session segment.
REFUEL_JUMP_KG = 1.5
# Tyre wear drops by more than this (percentage points) => fresh set.
FRESH_TYRE_DROP = 2.0
# Laps used for the representative pace of a run (fastest share).
PACE_SHARE = 0.6
BALANCE_MAX_LAPS = 8
# Lap classes (metrics.LAP_CLASSES) that never represent the car's pace on a run.
NON_RUN_CLASSES = frozenset({"start", "in", "pit", "out", "invalid"})

_STRENGTH_RANK = {"none": 0, "mild": 1, "medium": 2, "strong": 3}


@dataclass
class Run:
    session_id: int | None
    idx: int
    laps: list[int]
    setup: dict[str, float]
    mech_fp: str | None
    compound: int | None
    fuel_kg: float | None
    kind: str  # quali | race
    best_lap: int
    best_time: float
    best_corrected: float
    median_corrected: float
    lap_std: float
    deg_s_per_lap: float | None
    wear_pct_per_lap: float | None
    balance: dict[str, Any] = field(default_factory=dict)
    temp_front: float | None = None
    temp_rear: float | None = None
    lockup_frac: float | None = None
    conditions_state: str = "dry"
    session_type: str = ""
    corrected_times: list[float] = field(default_factory=list)

    @property
    def n_laps(self) -> int:
        return len(self.laps)

    @property
    def label(self) -> str:
        return f"Run {self.idx + 1} · L{self.laps[0]}–{self.laps[-1]}"


def _lap_fuel(row: pd.Series, setup: dict[str, float]) -> float | None:
    """Fuel in the tank at lap start; falls back to the garage fuel when the reading is junk."""
    v = row.get("fuel_start")
    if v is not None and pd.notna(v) and float(v) > 0:
        return float(v)
    fs = setup.get("fuel_setup")
    return float(fs) if fs is not None and fs > 0 else None


def _slope(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 4:
        return None
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 4:
        return None
    return float(np.polyfit(x[ok], y[ok], 1)[0])


def _aggregate_balance(per_lap: list[dict[str, Any]]) -> dict[str, Any]:
    per_lap = [b for b in per_lap if b]
    if not per_lap:
        return {}
    out: dict[str, Any] = {}
    for key in ("entry_score", "mid_score", "exit_score"):
        vals = [b[key] for b in per_lap if b.get(key) is not None and np.isfinite(b[key])]
        out[key] = float(np.median(vals)) if vals else 0.0
    votes = Counter(str(b.get("issue") or "balanced") for b in per_lap if (b.get("issue") or "balanced") != "balanced")
    if votes:
        issue = votes.most_common(1)[0][0]
        matching = [b for b in per_lap if b.get("issue") == issue]
        out["issue"] = issue
        out["issue_phase"] = Counter(str(b.get("issue_phase") or "all") for b in matching).most_common(1)[0][0]
        out["issue_strength"] = max(
            (str(b.get("issue_strength") or "mild") for b in matching), key=lambda s: _STRENGTH_RANK.get(s, 0)
        )
    else:
        out["issue"], out["issue_phase"], out["issue_strength"] = "balanced", "all", "none"
    return out


def _build_run(
    df: pd.DataFrame,
    rows: list[pd.Series],
    setups: list[dict[str, float]],
    *,
    idx: int,
    session: dict[str, Any] | None,
) -> Run:
    laps = [int(r["lap"]) for r in rows]
    fuels = [_lap_fuel(r, s) for r, s in zip(rows, setups)]
    raw = [float(r["lap_time"]) for r in rows]
    corrected = [fuel_corrected_time(t, f) for t, f in zip(raw, fuels)]

    order = np.argsort(corrected)
    n_pace = max(1, int(round(len(corrected) * PACE_SHARE)))
    pace = [corrected[i] for i in order[:n_pace]]
    best_i = int(order[0])

    fuel_start = next((f for f in fuels if f is not None), None)
    n = len(rows)
    is_race = (fuel_start is not None and fuel_start >= RACE_FUEL_KG) or n >= RACE_MIN_LAPS

    wear = [float(r["tyre_wear_avg"]) if pd.notna(r.get("tyre_wear_avg")) else np.nan for r in rows]
    wear = [w if (np.isfinite(w) and w >= 0) else np.nan for w in wear]

    # Balance on the fastest laps only (analysis is per-lap and not free).
    bal_laps = [laps[i] for i in order[: min(n, BALANCE_MAX_LAPS)]]
    per_lap_bal = [analyze_practice_balance(df, lap=lap) or {} for lap in bal_laps]
    balance = _aggregate_balance(per_lap_bal)
    tf = [b["temp_front"] for b in per_lap_bal if b.get("temp_front") is not None]
    tr = [b["temp_rear"] for b in per_lap_bal if b.get("temp_rear") is not None]
    lk = [b["lockup_frac"] for b in per_lap_bal if b.get("lockup_frac") is not None]

    setup = setups[best_i]
    compound = rows[0].get("compound")
    return Run(
        session_id=int(session["id"]) if session and session.get("id") is not None else None,
        idx=idx,
        laps=laps,
        setup=setup,
        mech_fp=mech_fingerprint(setup),
        compound=int(compound) if compound is not None and pd.notna(compound) else None,
        fuel_kg=fuel_start,
        kind="race" if is_race else "quali",
        best_lap=laps[best_i],
        best_time=float(min(raw)),
        best_corrected=float(corrected[best_i]),
        median_corrected=float(np.median(pace)),
        lap_std=float(np.std(pace, ddof=1)) if len(pace) >= 2 else 0.0,
        deg_s_per_lap=_slope(list(range(n)), corrected),
        wear_pct_per_lap=_slope(list(range(n)), wear),
        balance=balance,
        temp_front=float(np.median(tf)) if tf else None,
        temp_rear=float(np.median(tr)) if tr else None,
        lockup_frac=float(np.mean(lk)) if lk else None,
        conditions_state=_as_state((session or {}).get("conditions")),
        session_type=str((session or {}).get("session_type") or ""),
        corrected_times=[float(c) for c in corrected],
    )


def split_runs(
    df: pd.DataFrame,
    *,
    session: dict[str, Any] | None = None,
    track_length: float | None = None,
) -> list[Run]:
    """
    Group consecutive probable laps that share a mechanical setup, tyre compound and tyre set.

    A gap in lap numbers (takeback), a refuel jump or a fresh tyre set also starts a new run.
    Standing-start, in, pit, out and invalid laps are left out (and so split runs too).
    Sessions without per-lap garage channels use the stored setup_json.
    """
    summary = build_lap_summary(df, track_length=track_length)
    if summary.empty:
        return []

    stored = parse_setup_json((session or {}).get("setup_json"))
    per_lap_channels = has_telemetry_setup(df)

    runs: list[Run] = []
    cur_rows: list[pd.Series] = []
    cur_setups: list[dict[str, float]] = []
    prev: pd.Series | None = None
    prev_fp: str | None = None

    def flush() -> None:
        if cur_rows:
            runs.append(_build_run(df, list(cur_rows), list(cur_setups), idx=len(runs), session=session))
        cur_rows.clear()
        cur_setups.clear()

    for _, row in summary.iterrows():
        if row.get("lap_class") in NON_RUN_CLASSES:
            continue  # the next kept lap is no longer consecutive, so it opens a new run
        lap = int(row["lap"])
        setup, _src = resolve_session_setup(stored, df, lap)
        fp = mech_fingerprint(setup) if per_lap_channels else prev_fp or mech_fingerprint(setup)

        new_run = prev is None
        if prev is not None:
            if lap != int(prev["lap"]) + 1 or bool(row.get("fresh_set")):
                new_run = True
            elif fp != prev_fp:
                new_run = True
            elif row.get("compound") != prev.get("compound"):
                new_run = True
            else:
                f_now, f_prev = row.get("fuel_start"), prev.get("fuel_start")
                if pd.notna(f_now) and pd.notna(f_prev) and float(f_now) - float(f_prev) > REFUEL_JUMP_KG:
                    new_run = True
                w_now, w_prev = row.get("tyre_wear_avg"), prev.get("tyre_wear_avg")
                if (
                    pd.notna(w_now)
                    and pd.notna(w_prev)
                    and float(w_prev) >= 0
                    and float(w_now) >= 0
                    and float(w_prev) - float(w_now) > FRESH_TYRE_DROP
                ):
                    new_run = True
        if new_run:
            flush()
        cur_rows.append(row)
        cur_setups.append(setup)
        prev, prev_fp = row, fp
    flush()
    return runs


def best_run(runs: list[Run], mode: str) -> Run | None:
    """Best run of a kind: quali by best corrected lap, race by median corrected pace (>=3 laps preferred)."""
    pool = [r for r in runs if r.kind == mode]
    if not pool:
        return None
    if mode == "race":
        long_runs = [r for r in pool if r.n_laps >= 3]
        pool = long_runs or pool
        return min(pool, key=lambda r: r.median_corrected)
    return min(pool, key=lambda r: r.best_corrected)


def runs_frame(runs: list[Run]) -> pd.DataFrame:
    """Display table for the GUI."""
    rows = []
    for r in runs:
        rows.append(
            {
                "Run": r.idx + 1,
                "Laps": f"{r.laps[0]}–{r.laps[-1]} ({r.n_laps})",
                "Type": r.kind,
                "Compound": c_label(r.compound),
                "Fuel (kg)": round(r.fuel_kg, 1) if r.fuel_kg is not None else None,
                "Best": round(r.best_time, 3),
                "Best (fuel-corr.)": round(r.best_corrected, 3),
                "Pace (fuel-corr.)": round(r.median_corrected, 3),
                "Deg s/lap": round(r.deg_s_per_lap, 3) if r.deg_s_per_lap is not None else None,
                "Balance": (
                    f"{r.balance.get('issue')} ({r.balance.get('issue_phase')}, {r.balance.get('issue_strength')})"
                    if r.balance.get("issue") not in (None, "balanced")
                    else "balanced"
                ),
                "Setup": r.mech_fp[:6] if r.mech_fp else "—",
            }
        )
    return pd.DataFrame(rows)
