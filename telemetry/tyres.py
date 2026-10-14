"""
Tyre engineering: stints, per-wheel lap data, operating windows, pressures, degradation and the
per-track compound model the strategy tool runs on.

Wheel index order is the export's: 0=RL, 1=RR, 2=FL, 3=FR (channels.WHEELS).
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .channels import WHEELS, primary_tyre_temp, temp_kind, wheel_columns
from .compounds import WET_CODES, Allocation, c_label, get_allocation, is_slick, softness
from .conditions import _as_state
from .corners import normalize_track_name
from .db import ANALYSIS_COLUMNS, connect, get_session, load_session_telemetry
from .metrics import FUEL_S_PER_KG, build_lap_summary, fuel_corrected_time
from .setup_history import parse_setup_json
from .setup_tweaker import pa_to_psi

# Max-wheel wear at which a stint is considered done (editable in the UI). Library race stints
# were boxed at 55-66%.
WEAR_LIMIT_PCT = 65.0
PUSH_CLASSES = frozenset({"push"})
MIN_DEG_LAPS = 3
MIN_MODEL_LAPS = 4  # push laps a stint needs to feed the track compound model
# Fallback when a compound has no measured long run: one softness step = this much quicker,
# and degradation / wear scale by these factors per step.
ASSUMED_PACE_STEP_S = -0.45
ASSUMED_DEG_FACTOR = 1.5
ASSUMED_WEAR_FACTOR = 1.35
# Laps of evidence the softness-step prior is worth when blending a measured compound offset.
OFFSET_PRIOR_LAPS = 10
# F1 UDP weather: 0 clear, 1 light cloud, 2 overcast, 3 light rain, 4 heavy rain, 5 storm.
RAIN_WEATHER = 3
# Starting windows only (the engineer sets their own per compound). The carcass runs ~15-25 °C
# above the surface in the library exports, so the window depends on which channel is shown.
DEFAULT_TEMP_WINDOW = {
    "surface": {"slick": (80.0, 100.0), "inter": (60.0, 80.0), "wet": (45.0, 65.0)},
    "inner": {"slick": (90.0, 105.0), "inter": (70.0, 90.0), "wet": (55.0, 75.0)},
}

TARGETS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tyre_targets (
    compound INTEGER PRIMARY KEY,
    temp_lo REAL,
    temp_hi REAL,
    hot_front_psi REAL,
    hot_rear_psi REAL,
    updated_at TEXT NOT NULL
);
"""


# --------------------------------------------------------------------------- targets


@dataclass
class TyreTargets:
    compound: int | None
    temp_lo: float
    temp_hi: float
    hot_front_psi: float | None = None
    hot_rear_psi: float | None = None
    source: str = "default"

    def hot_target(self, wheel: int) -> float | None:
        return self.hot_front_psi if wheel in (2, 3) else self.hot_rear_psi


def _family(code: int | None) -> str:
    if code == 7:
        return "inter"
    if code == 8:
        return "wet"
    return "slick"


def get_targets(compound: int | None, app_root: Path | None = None, *, kind: str = "surface") -> TyreTargets:
    """Saved targets for a compound, else the default window for this temperature channel kind."""
    lo, hi = DEFAULT_TEMP_WINDOW.get(kind, DEFAULT_TEMP_WINDOW["surface"])[_family(compound)]
    if compound is None:
        return TyreTargets(None, lo, hi)
    with connect(app_root) as conn:
        conn.executescript(TARGETS_SCHEMA)
        row = conn.execute("SELECT * FROM tyre_targets WHERE compound = ?", (int(compound),)).fetchone()
    if not row:
        return TyreTargets(int(compound), lo, hi)
    return TyreTargets(
        int(compound),
        float(row["temp_lo"]) if row["temp_lo"] is not None else lo,
        float(row["temp_hi"]) if row["temp_hi"] is not None else hi,
        row["hot_front_psi"],
        row["hot_rear_psi"],
        "saved",
    )


def save_targets(t: TyreTargets, app_root: Path | None = None) -> None:
    if t.compound is None:
        return
    with connect(app_root) as conn:
        conn.executescript(TARGETS_SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO tyre_targets (compound, temp_lo, temp_hi, hot_front_psi, hot_rear_psi, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (int(t.compound), t.temp_lo, t.temp_hi, t.hot_front_psi, t.hot_rear_psi, datetime.now(timezone.utc).isoformat()),
        )


# --------------------------------------------------------------------------- stints


@dataclass
class Stint:
    idx: int
    laps: list[int]  # every lap on this tyre set, incl. in / pit / out laps
    compound: int | None
    push_laps: list[int] = field(default_factory=list)
    ages: dict[int, int] = field(default_factory=dict)  # lap -> laps on this set before it

    @property
    def n_laps(self) -> int:
        return len(self.laps)

    def label(self, alloc: Allocation | None = None) -> str:
        return alloc.label(self.compound) if alloc else c_label(self.compound)


def tyre_stints(summary: pd.DataFrame) -> list[Stint]:
    """
    Consecutive laps on one tyre set; a new set starts at each `fresh_set` lap.

    Ages are the game's tyre age when the export logs it (a used set starts above 0, and laps
    the export skipped still count), else laps since the set was fitted.
    """
    if summary.empty:
        return []
    s = summary.sort_values("lap").reset_index(drop=True)
    groups: list[list[int]] = []
    for i, row in s.iterrows():
        if i == 0 or bool(row.get("fresh_set")):
            groups.append([])
        groups[-1].append(i)
    stints = []
    for k, rows in enumerate(groups):
        part = s.loc[rows]
        comp = pd.to_numeric(part.get("compound", pd.Series(dtype=float)), errors="coerce")
        comp = comp[comp >= 0]
        compound = int(comp.mode().iloc[0]) if not comp.empty else None
        laps = [int(x) for x in part["lap"]]
        cls = part["lap_class"] if "lap_class" in part.columns else pd.Series(["push"] * len(part), index=part.index)
        game_age = part["tyre_age"].to_numpy(dtype=float) if "tyre_age" in part.columns else np.full(len(part), np.nan)
        if np.isfinite(game_age).all():
            ages = {lap: int(a) for lap, a in zip(laps, game_age)}
        else:
            ages = {lap: j for j, lap in enumerate(laps)}
        stints.append(
            Stint(
                idx=k,
                laps=laps,
                compound=compound,
                push_laps=[int(l) for l, c in zip(part["lap"], cls) if c in PUSH_CLASSES],
                ages=ages,
            )
        )
    return stints


# --------------------------------------------------------------------------- per-wheel lap table


def _num(frame: pd.DataFrame, col: str) -> np.ndarray:
    v = frame[col].to_numpy(dtype=float, na_value=np.nan)
    return v[np.isfinite(v)]


def _valid_rows(lap_df: pd.DataFrame) -> pd.DataFrame:
    """Drop pre-start / post-session garbage rows (compound or fuel < 0)."""
    ok = np.ones(len(lap_df), dtype=bool)
    for col in ("tyre_compound_0", "fuel"):
        if col in lap_df.columns:
            ok &= lap_df[col].to_numpy(dtype=float, na_value=np.nan) >= 0
    return lap_df.loc[ok]


def _cold_pressures(df: pd.DataFrame, session: dict[str, Any] | None) -> dict[int, float]:
    """Garage (cold) pressure per wheel in psi: per-lap setup channels, else the stored setup."""
    cols = [f"tyre_press_setup_{i}" for i in range(4)]
    out: dict[int, float] = {}
    if all(c in df.columns for c in cols):
        for i, c in enumerate(cols):
            v = pd.to_numeric(df[c], errors="coerce")
            v = v[v > 1000]
            if not v.empty:
                out[i] = pa_to_psi(float(v.median()))
    if not out and session:
        setup = parse_setup_json(session.get("setup_json"))
        for i, c in enumerate(cols):
            v = setup.get(c)
            if v is not None and float(v) > 1000:
                out[i] = pa_to_psi(float(v))
    return out


def wheel_lap_table(
    df: pd.DataFrame,
    summary: pd.DataFrame,
    *,
    stints: list[Stint] | None = None,
    targets: TyreTargets | None = None,
    fuel_k: float = FUEL_S_PER_KG,
) -> pd.DataFrame:
    """
    One row per lap: class, stint, tyre age, fuel-corrected time, and per wheel the mean / p98
    temperature, % of the lap inside the temperature window, hot pressure (psi) and wear.
    """
    if summary.empty:
        return pd.DataFrame()
    stints = stints if stints is not None else tyre_stints(summary)
    stint_of = {lap: s for s in stints for lap in s.laps}
    temp = primary_tyre_temp(df)
    press_cols = wheel_columns(df, "tyre_press")
    wear_cols = wheel_columns(df, "tyre_wear")
    wanted = set(summary["lap"].astype(int))
    by_lap = {int(lap): g for lap, g in df.groupby("lap", sort=False) if int(lap) in wanted}
    rows = []
    for _, lap_row in summary.sort_values("lap").iterrows():
        lap = int(lap_row["lap"])
        lap_df = _valid_rows(by_lap.get(lap, df.iloc[0:0]))
        st_ = stint_of.get(lap)
        row: dict[str, Any] = {
            "lap": lap,
            "lap_class": lap_row.get("lap_class", "push"),
            "stint": st_.idx + 1 if st_ else None,
            "age": st_.ages.get(lap) if st_ else None,
            "compound": st_.compound if st_ else lap_row.get("compound"),
            "lap_time": float(lap_row["lap_time"]),
            "fuel_start": lap_row.get("fuel_start"),
            "corr_time": fuel_corrected_time(float(lap_row["lap_time"]), lap_row.get("fuel_start"), s_per_kg=fuel_k),
        }
        tlo, thi = (targets.temp_lo, targets.temp_hi) if targets else DEFAULT_TEMP_WINDOW[temp_kind(temp[0] if temp else None)]["slick"]
        reset = bool(lap_row.get("pit_stop") or lap_row.get("fresh_set"))
        for i, w in enumerate(WHEELS):
            if temp:
                t = _num(lap_df, temp[1][i])
                t = t[t > 0]
                row[f"T_{w}"] = float(t.mean()) if t.size else np.nan
                row[f"Tpk_{w}"] = float(np.quantile(t, 0.98)) if t.size else np.nan
                row[f"Twin_{w}"] = float(((t >= tlo) & (t <= thi)).mean() * 100) if t.size else np.nan
            if press_cols:
                p = _num(lap_df, press_cols[i])
                p = p[p > 1000]
                row[f"P_{w}"] = pa_to_psi(float(np.median(p))) if p.size else np.nan
            if wear_cols:
                wv = _num(lap_df, wear_cols[i])
                wv = wv[wv >= 0]
                if wv.size:
                    row[f"W_{w}"] = float(wv[-1] * 100)
                    row[f"dW_{w}"] = np.nan if reset else float((wv[-1] - wv[0]) * 100)
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- degradation


@dataclass
class DegFit:
    slope: float | None  # s per lap of tyre age (fuel-corrected)
    intercept: float | None  # corrected time at age 0
    r2: float | None
    n: int
    cliff_age: int | None = None  # age where a steeper second slope starts


def fit_degradation(ages: np.ndarray, times: np.ndarray) -> DegFit:
    """Straight line of fuel-corrected lap time vs tyre age, plus a simple two-segment cliff check."""
    ages = np.asarray(ages, dtype=float)
    times = np.asarray(times, dtype=float)
    ok = np.isfinite(ages) & np.isfinite(times)
    ages, times = ages[ok], times[ok]
    n = len(ages)
    if n < MIN_DEG_LAPS or np.ptp(ages) == 0:
        return DegFit(None, None, None, n)
    slope, intercept = np.polyfit(ages, times, 1)
    pred = intercept + slope * ages
    ss_res = float(np.sum((times - pred) ** 2))
    ss_tot = float(np.sum((times - times.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    cliff = None
    if n >= 7:
        order = np.argsort(ages)
        a, t = ages[order], times[order]
        best = None
        for k in range(3, n - 2):
            s1, i1 = np.polyfit(a[:k], t[:k], 1)
            s2, i2 = np.polyfit(a[k:], t[k:], 1)
            sse = float(np.sum((t[:k] - (i1 + s1 * a[:k])) ** 2) + np.sum((t[k:] - (i2 + s2 * a[k:])) ** 2))
            if s2 > 2 * max(s1, 0.02) and sse < 0.6 * ss_res and (best is None or sse < best[0]):
                best = (sse, int(a[k]))
        if best:
            cliff = best[1]
    return DegFit(float(slope), float(intercept), r2, n, cliff)


def _wear_rate(wheel_tbl: pd.DataFrame, laps: list[int], wheel: str) -> float | None:
    """%/lap from end-of-lap wear vs lap number over the stint (pit laps excluded)."""
    col = f"W_{wheel}"
    if col not in wheel_tbl.columns:
        return None
    part = wheel_tbl[wheel_tbl["lap"].isin(laps) & ~wheel_tbl["lap_class"].isin(["pit", "invalid"])]
    part = part[part[col].notna()]
    # Practice exports can log the same game tyre age on every lap: no slope to fit.
    if len(part) < 2 or np.ptp(part["age"].to_numpy(dtype=float)) == 0:
        return None
    slope = np.polyfit(part["age"].astype(float), part[col].astype(float), 1)[0]
    return float(max(0.0, slope))


@dataclass
class StintSummary:
    stint: Stint
    deg: DegFit
    wear_rate: dict[str, float | None]
    limiting_wheel: str | None
    wear_now: float | None  # max-wheel wear at the end of the stint
    laps_to_limit: float | None
    temp_mean: dict[str, float | None]
    temp_in_window: dict[str, float | None]
    hot_psi: dict[str, float | None]
    cold_psi: dict[int, float]
    warmup_s: float | None  # first push lap vs the stint line (cold tyres / out-lap loss)
    fuel_per_lap: float | None


def summarize_stints(
    df: pd.DataFrame,
    summary: pd.DataFrame,
    *,
    session: dict[str, Any] | None = None,
    wear_limit: float = WEAR_LIMIT_PCT,
    targets: TyreTargets | None = None,
    fuel_k: float = FUEL_S_PER_KG,
) -> tuple[list[StintSummary], pd.DataFrame]:
    stints = tyre_stints(summary)
    tbl = wheel_lap_table(df, summary, stints=stints, targets=targets, fuel_k=fuel_k)
    cold = _cold_pressures(df, session)
    out = []
    for s in stints:
        push = tbl[tbl["lap"].isin(s.push_laps)]
        deg = fit_degradation(push["age"].to_numpy(dtype=float), push["corr_time"].to_numpy(dtype=float))
        rates = {w: _wear_rate(tbl, s.laps, w) for w in WHEELS}
        known = {w: r for w, r in rates.items() if r is not None}
        limiting = max(known, key=known.get) if known else None
        on_set = tbl[tbl["lap"].isin(s.laps)]
        wear_cols = [f"W_{w}" for w in WHEELS if f"W_{w}" in on_set.columns]
        # Max over the stint, not the last lap: a late stop ends that lap on the new (0%) set.
        wear_now = float(on_set[wear_cols].max().max()) if wear_cols and not on_set.empty else None
        laps_to_limit = None
        if limiting and known[limiting] > 1e-6 and wear_now is not None:
            laps_to_limit = max(0.0, (wear_limit - wear_now) / known[limiting])
        warmup = None
        if deg.slope is not None and not push.empty:
            first = push.sort_values("age").iloc[0]
            if first["age"] <= 2:
                warmup = float(first["corr_time"] - (deg.intercept + deg.slope * first["age"]))
        fuel = summary[summary["lap"].isin(s.push_laps)]["fuel_used"] if "fuel_used" in summary.columns else pd.Series(dtype=float)
        fuel = fuel[(fuel > 0) & (fuel < 20)]
        out.append(
            StintSummary(
                stint=s,
                deg=deg,
                wear_rate=rates,
                limiting_wheel=limiting,
                wear_now=wear_now,
                laps_to_limit=laps_to_limit,
                temp_mean={w: _median(push, f"T_{w}") for w in WHEELS},
                temp_in_window={w: _median(push, f"Twin_{w}") for w in WHEELS},
                hot_psi={w: _median(push, f"P_{w}") for w in WHEELS},
                cold_psi=cold,
                warmup_s=warmup,
                fuel_per_lap=float(fuel.median()) if not fuel.empty else None,
            )
        )
    return out, tbl


def _median(frame: pd.DataFrame, col: str) -> float | None:
    if col not in frame.columns:
        return None
    v = frame[col].dropna()
    return float(v.median()) if not v.empty else None


# --------------------------------------------------------------------------- pressures


def pressure_recommendation(
    hot_psi: dict[str, float | None],
    cold_psi: dict[int, float],
    targets: TyreTargets,
    *,
    step_psi: float = 0.1,
) -> pd.DataFrame:
    """Cold set needed to hit the hot target: cold_new = cold_now + (target_hot - measured_hot)."""
    rows = []
    for i, w in enumerate(WHEELS):
        hot = hot_psi.get(w)
        cold = cold_psi.get(i)
        target = targets.hot_target(i)
        build = hot - cold if hot is not None and cold is not None else None
        new = None
        if hot is not None and cold is not None and target is not None:
            new = round((cold + (target - hot)) / step_psi) * step_psi
        rows.append(
            {
                "Wheel": w,
                "Cold set (psi)": cold,
                "Hot measured (psi)": hot,
                "Build-up (psi)": build,
                "Hot target (psi)": target,
                "Cold set → (psi)": new,
                "Change (psi)": (new - cold) if new is not None and cold is not None else None,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- track compound model


@dataclass
class CompoundModel:
    code: int
    label: str
    color: str
    offset_s: float  # vs the reference compound at the same tyre age and fuel
    deg_s_per_lap: float
    wear_pct_per_lap: float | None
    warmup_s: float
    n_stints: int
    n_laps: int
    source: str  # measured | assumed | manual
    note: str = ""

    def max_laps(self, wear_limit: float = WEAR_LIMIT_PCT) -> int | None:
        if not self.wear_pct_per_lap or self.wear_pct_per_lap <= 1e-6:
            return None
        return int(wear_limit / self.wear_pct_per_lap)


@dataclass
class TrackTyreModel:
    track: str
    state: str
    base_pace_s: float | None  # reference compound, new tyre, ref fuel (5 kg)
    ref_compound: int | None
    compounds: dict[int, CompoundModel]
    pit_losses: list[float]
    fuel_per_lap: float | None
    race_laps_seen: int | None
    allocation: Allocation
    sources: list[int] = field(default_factory=list)  # session ids that fed the model
    sc_pit_losses: list[float] = field(default_factory=list)  # stops made behind the safety car
    stats: RaceStats | None = None  # library-wide fuel effect and box wear the model used

    @property
    def pit_loss(self) -> float | None:
        return float(np.median(self.pit_losses)) if self.pit_losses else None

    @property
    def sc_pit_factor(self) -> float | None:
        """Measured SC pit loss as a share of the green-flag loss."""
        if not self.sc_pit_losses or not self.pit_loss:
            return None
        return float(np.clip(np.median(self.sc_pit_losses) / self.pit_loss, 0.2, 1.0))


# Full frames are big (a race is ~160k rows); keep only a few. Summaries and stint tables are
# small, so every session's can stay cached — stored sessions never change after import.
@lru_cache(maxsize=4)
def _session_frames(app_root: str, session_id: int) -> tuple[dict[str, Any] | None, pd.DataFrame, pd.DataFrame]:
    root = Path(app_root) if app_root else None
    session = get_session(session_id, root)
    if not session:
        return None, pd.DataFrame(), pd.DataFrame()
    df = load_session_telemetry(session_id, root, columns=ANALYSIS_COLUMNS)
    return session, df, build_lap_summary(df, track_length=session.get("track_length"))


def session_frames(session_id: int, app_root: Path | None = None) -> tuple[dict[str, Any] | None, pd.DataFrame, pd.DataFrame]:
    """(session, analysis channels, lap summary) for a stored session."""
    return _session_frames(str(app_root) if app_root else "", int(session_id))


@lru_cache(maxsize=512)
def _session_summary(app_root: str, session_id: int) -> tuple[dict[str, Any] | None, pd.DataFrame]:
    root = Path(app_root) if app_root else None
    session = get_session(session_id, root)
    if not session:
        return None, pd.DataFrame()
    df = load_session_telemetry(session_id, root, columns=ANALYSIS_COLUMNS)
    return session, build_lap_summary(df, track_length=session.get("track_length"))


def session_summary(session_id: int, app_root: Path | None = None) -> tuple[dict[str, Any] | None, pd.DataFrame]:
    """(session, lap summary) without keeping the telemetry in memory."""
    return _session_summary(str(app_root) if app_root else "", int(session_id))


@lru_cache(maxsize=512)
def _session_stints(app_root: str, session_id: int, fuel_k: float, wear_limit: float):
    root = Path(app_root) if app_root else None
    session = get_session(session_id, root)
    if not session:
        return None, pd.DataFrame(), [], pd.DataFrame()
    df = load_session_telemetry(session_id, root, columns=ANALYSIS_COLUMNS)
    summary = build_lap_summary(df, track_length=session.get("track_length"))
    summaries, tbl = summarize_stints(df, summary, session=session, wear_limit=wear_limit, fuel_k=fuel_k)
    return session, summary, summaries, tbl


def clear_cache() -> None:
    _session_frames.cache_clear()
    _session_summary.cache_clear()
    _session_stints.cache_clear()
    _cached_model.cache_clear()
    _cached_race_stats.cache_clear()


def measure_pit_losses(summary: pd.DataFrame, *, under_sc: bool = False) -> list[float]:
    """
    Time lost to each stop: laps [stop-1, stop, stop+1] minus the push pace around them.

    Covers both timing-line layouts (line in the pit lane or before it) without knowing which.
    Stops whose window has safety-car laps are counted separately (`under_sc=True`); windows
    with a lap missing from the export are skipped.
    """
    if summary.empty or "pit_stop" not in summary.columns:
        return []
    s = summary.sort_values("lap").reset_index(drop=True)
    push = s[s["lap_class"] == "push"]
    out = []
    for _, stop in s[s["pit_stop"]].iterrows():
        lap = int(stop["lap"])
        window = s[s["lap"].between(lap - 1, lap + 1)]
        near = push[push["lap"].between(lap - 6, lap + 6) & ~push["lap"].between(lap - 1, lap + 1)]
        if len(window) < 3 or len(near) < 2 or (window["lap_class"] == "invalid").any():
            continue
        if bool((window["lap_class"] == "sc").any()) != under_sc:
            continue
        out.append(float(window["lap_time"].sum() - len(window) * near["lap_time"].median()))
    return out


def _stint_eligible(stint: Stint, summary: pd.DataFrame, state: str, session_state: str) -> bool:
    """
    Whether a stint describes the requested track state. Dry: slicks, in a session not tagged
    wet, with no rain logged on its push laps. Inter / wet: that compound, whatever the tag.
    """
    code = stint.compound
    if code is None:
        return False
    if state == "dry":
        if not is_slick(code) or session_state in ("damp", "inter", "wet"):
            return False
        if "weather" in summary.columns:
            wx = summary.loc[summary["lap"].isin(stint.push_laps), "weather"].to_numpy(dtype=float)
            if np.isfinite(wx).any() and np.nanmax(wx) >= RAIN_WEATHER:
                return False
        return True
    if state == "inter":
        return code == 7
    if state == "wet":
        return code == 8
    return session_state == state


def _stint_points(sessions: pd.DataFrame, state: str, app_root: Path | None, wear_limit: float, fuel_k: float):
    """Per-stint degradation inputs from every session on the track in the same track state."""
    points = []  # (session_id, compound, ages, corr_times, wear_rate, warmup)
    pit_losses: list[float] = []
    sc_losses: list[float] = []
    fuel: list[float] = []
    race_laps: list[int] = []
    used: list[int] = []
    for _, row in sessions.iterrows():
        session_state = _as_state(row.get("conditions"))
        if state == "damp" and session_state != "damp":
            continue
        try:
            session, summary, summaries, tbl = _session_stints(
                str(app_root) if app_root else "", int(row["id"]), float(fuel_k), float(wear_limit)
            )
        except FileNotFoundError:
            continue
        if session is None or summary.empty or "lap_class" not in summary.columns:
            continue
        losses = measure_pit_losses(summary)
        sc_here = measure_pit_losses(summary, under_sc=True)
        is_race = str(session.get("session_type") or "") == "Race" or bool(summary["pit_stop"].any())
        took = False
        for ss in summaries:
            s = ss.stint
            if len(s.push_laps) < MIN_MODEL_LAPS or not _stint_eligible(s, summary, state, session_state):
                continue
            push = tbl[tbl["lap"].isin(s.push_laps)]
            rate = ss.wear_rate.get(ss.limiting_wheel) if ss.limiting_wheel else None
            points.append(
                (int(row["id"]), s.compound, push["age"].to_numpy(float), push["corr_time"].to_numpy(float), rate, ss.warmup_s, is_race)
            )
            took = True
        if took or session_state == state:  # pit losses only from sessions run in this state
            pit_losses += losses
            sc_losses += sc_here
        if is_race:
            f = summary.loc[summary["lap_class"] == "push", "fuel_used"] if "fuel_used" in summary.columns else pd.Series(dtype=float)
            fuel += [float(v) for v in f if 0 < v < 20]
            race_laps.append(int(summary["lap"].max()) + 1)
        if took:
            used.append(int(row["id"]))
    return points, pit_losses, sc_losses, fuel, race_laps, used


@dataclass(frozen=True)
class RaceStats:
    """Library-wide race behaviour the per-track models lean on."""

    fuel_s_per_kg: float  # fuel + track-evolution effect used to correct lap times
    fuel_pairs: int  # same-compound stint pairs it was measured from (0 = default)
    box_wear_pct: float | None  # 75th percentile of max-wheel wear when a dry set was boxed
    n_stops: int


FUEL_EFFECT_RANGE = (0.02, 0.15)
MIN_FUEL_PAIRS = 3
MIN_FUEL_GAP_KG = 4.0


def default_wear_limit(stats: RaceStats | None) -> float:
    """Where you actually box (75th percentile of max-wheel wear at a stop), else the fallback."""
    if stats is not None and stats.box_wear_pct:
        return float(np.clip(round(stats.box_wear_pct), 55, 85))
    return WEAR_LIMIT_PCT


def library_race_stats(app_root: Path | None = None) -> RaceStats:
    from .db import list_sessions

    sessions = list_sessions(app_root)
    sig = tuple(int(i) for i in sessions["id"]) if not sessions.empty else ()
    return _cached_race_stats(str(app_root) if app_root else "", sig)


@lru_cache(maxsize=8)
def _cached_race_stats(app_root: str, session_ids: tuple[int, ...]) -> RaceStats:
    """
    Fuel effect: two stints on the same compound in one race, at different fuel loads, differ at
    tyre age 0 only by fuel (and track evolution) — the slope of that gap per kg is the effect.
    """
    root = Path(app_root) if app_root else None
    ks: list[float] = []
    box: list[float] = []
    for sid in session_ids:
        try:
            _, summary = session_summary(sid, root)
        except FileNotFoundError:
            continue
        if summary.empty or "pit_stop" not in summary.columns or not summary["pit_stop"].any():
            continue
        rows = []
        stints = tyre_stints(summary)
        for k, st in enumerate(stints):
            part = summary[summary["lap"].isin(st.laps)]
            if k < len(stints) - 1 and is_slick(st.compound) and "tyre_wear_max" in part.columns:
                w = part["tyre_wear_max"].to_numpy(dtype=float)
                if np.isfinite(w).any():
                    box.append(float(np.nanmax(w)))
            p = summary[summary["lap"].isin(st.push_laps)]
            if len(p) < MIN_MODEL_LAPS or "fuel_start" not in p.columns:
                continue
            age = np.array([st.ages[lap] for lap in p["lap"]], dtype=float)
            t = p["lap_time"].to_numpy(dtype=float)
            f = p["fuel_start"].to_numpy(dtype=float)
            if np.ptp(age) == 0 or not np.isfinite(f).all() or (f <= 0).any():
                continue
            rows.append((st.compound, np.polyfit(age, t, 1)[1], np.polyval(np.polyfit(age, f, 1), 0)))
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                if rows[i][0] == rows[j][0] and abs(rows[i][2] - rows[j][2]) > MIN_FUEL_GAP_KG:
                    ks.append((rows[i][1] - rows[j][1]) / (rows[i][2] - rows[j][2]))
    if len(ks) >= MIN_FUEL_PAIRS:
        k, n = float(np.clip(np.median(ks), *FUEL_EFFECT_RANGE)), len(ks)
    else:
        k, n = FUEL_S_PER_KG, 0
    box_p75 = float(np.percentile(box, 75)) if len(box) >= 3 else None
    return RaceStats(fuel_s_per_kg=k, fuel_pairs=n, box_wear_pct=box_p75, n_stops=len(box))


def _assume(code: int, known: dict[int, float], step) -> float | None:
    """
    Value for a compound that was never run, from the measured ones: interpolated in softness
    between the nearest softer and harder compound, else ``step(nearest, softness steps away)``.
    So a medium between a measured soft and hard never wears faster than the soft.
    """
    if not known:
        return None
    s = softness(code)
    softer = [c for c in known if softness(c) > s]
    harder = [c for c in known if softness(c) < s]
    if softer and harder:
        a, b = min(softer, key=softness), max(harder, key=softness)
        w = (s - softness(b)) / (softness(a) - softness(b))
        return float(known[b] + w * (known[a] - known[b]))
    near = min(known, key=lambda c: abs(softness(c) - s))
    return float(step(known[near], s - softness(near)))


def track_compound_model(
    track: str,
    state: str = "dry",
    app_root: Path | None = None,
    *,
    wear_limit: float = WEAR_LIMIT_PCT,
) -> TrackTyreModel:
    """
    Pace offset, degradation and wear per compound on a track, pooled over the library.

    Degradation is one slope per compound with a separate intercept per stint (so track
    evolution and fuel strategy between sessions do not bend the slope). Compound offsets
    come from sessions that ran more than one compound; missing compounds are extrapolated
    from the measured ones by softness step and flagged `assumed`.
    """
    from .setup_eval import sessions_on_track

    alloc = get_allocation(track, app_root)
    sessions = sessions_on_track(track, app_root)
    library = tuple(
        (int(r["id"]), str(r.get("conditions") or ""), str(r.get("session_type") or "")) for _, r in sessions.iterrows()
    )
    roles = tuple(sorted(alloc.roles.items()))
    stats = library_race_stats(app_root)
    model = _cached_model(str(app_root) if app_root else "", track, state, float(wear_limit), library, roles, alloc.source, stats)
    return copy.deepcopy(model)


@lru_cache(maxsize=32)
def _cached_model(
    app_root: str,
    track: str,
    state: str,
    wear_limit: float,
    library: tuple[tuple[int, str, str], ...],
    roles: tuple[tuple[int, str], ...],
    alloc_source: str,
    stats: RaceStats,
) -> TrackTyreModel:
    """Keyed on the track's sessions (+ tags) and allocation, so a new import or retag rebuilds it."""
    from .setup_eval import sessions_on_track

    root = Path(app_root) if app_root else None
    alloc = Allocation(normalize_track_name(track) or track, dict(roles), alloc_source)
    sessions = sessions_on_track(track, root)
    points, pit_losses, sc_losses, fuel, race_laps, used = (
        _stint_points(sessions, state, root, wear_limit, stats.fuel_s_per_kg) if not sessions.empty else ([], [], [], [], [], [])
    )

    by_comp: dict[int, list] = {}
    for p in points:
        by_comp.setdefault(p[1], []).append(p)

    measured: dict[int, dict[str, Any]] = {}
    for code, pts in by_comp.items():
        num = den = 0.0
        n_laps = 0
        for _, _, ages, times, _, _, _ in pts:
            ok = np.isfinite(ages) & np.isfinite(times)
            a, t = ages[ok], times[ok]
            if len(a) < 2:
                continue
            num += float(np.sum((a - a.mean()) * (t - t.mean())))
            den += float(np.sum((a - a.mean()) ** 2))
            n_laps += len(a)
        slope = num / den if den > 0 else 0.0
        # (session, intercept at age 0, laps, race session?)
        intercepts = [
            (sid, float(np.mean(t[np.isfinite(t)]) - slope * np.mean(a[np.isfinite(t)])), int(np.isfinite(t).sum()), race)
            for sid, _, a, t, _, _, race in pts
            if np.isfinite(t).sum() >= 2
        ]
        rates = [p[4] for p in pts if p[4]]
        warm = [p[5] for p in pts if p[5] is not None]
        measured[code] = {
            "slope": max(0.0, slope),
            "intercepts": intercepts,
            "wear": float(np.median(rates)) if rates else None,
            "warmup": float(np.median(warm)) if warm else 0.0,
            "n_stints": len(pts),
            "n_laps": n_laps,
        }

    ref = max(measured, key=lambda c: measured[c]["n_laps"]) if measured else None
    offsets: dict[int, float] = {ref: 0.0} if ref is not None else {}
    offset_notes: dict[int, str] = {}
    if ref is not None:
        ref_by_session: dict[int, list[tuple[float, int]]] = {}
        for sid, icpt, n, _ in measured[ref]["intercepts"]:
            ref_by_session.setdefault(sid, []).append((icpt, n))
        for code, m in measured.items():
            if code == ref:
                continue
            pairs = [
                (icpt - float(np.mean([v for v, _ in ref_by_session[sid]])), min(n, sum(k for _, k in ref_by_session[sid])), race)
                for sid, icpt, n, race in m["intercepts"]
                if sid in ref_by_session
            ]
            # Race long runs beat practice (quali sims run other engine / ERS modes).
            if any(race for *_, race in pairs):
                pairs = [p for p in pairs if p[2]]
            if not pairs:
                continue
            meas = float(np.median([d for d, _, _ in pairs]))
            n_eff = sum(n for _, n, _ in pairs)
            prior = ASSUMED_PACE_STEP_S * (softness(code) - softness(ref))
            offsets[code] = (n_eff * meas + OFFSET_PRIOR_LAPS * prior) / (n_eff + OFFSET_PRIOR_LAPS)
            if abs(meas - prior) > 1.0:
                offset_notes[code] = (
                    f"Measured {meas:+.2f} s over {n_eff} laps, blended toward the {prior:+.2f} s softness step — check it."
                )

    ref_icpts = measured[ref]["intercepts"] if ref is not None else []
    race_icpts = [i for _, i, _, race in ref_icpts if race]
    base = float(np.median(race_icpts or [i for _, i, _, _ in ref_icpts])) if ref_icpts else None

    # Candidate compounds: the track allocation, else whatever was run.
    candidates = sorted(set(alloc.roles) | set(measured), key=softness, reverse=True)
    # Dry and damp races run slicks; inter / wet races choose between the two wet-weather tyres.
    candidates = [c for c in candidates if (c in WET_CODES) == (state in ("inter", "wet"))]
    models: dict[int, CompoundModel] = {}
    for code in candidates:
        m = measured.get(code)
        steps = softness(code) - softness(ref) if ref is not None else 0
        ref_m = measured.get(ref) if ref is not None else None
        if m and code in offsets:
            source = "measured"
            offset, deg, wear, warm = offsets[code], m["slope"], m["wear"], m["warmup"]
        elif m:
            # Degradation measured, but never run alongside the reference compound.
            source = "measured"
            offset, deg, wear, warm = ASSUMED_PACE_STEP_S * steps, m["slope"], m["wear"], m["warmup"]
        elif ref_m:
            source = "assumed"
            offset = _assume(code, {c: offsets.get(c, ASSUMED_PACE_STEP_S * (softness(c) - softness(ref))) for c in measured},
                             lambda v, k: v + ASSUMED_PACE_STEP_S * k)
            deg = _assume(code, {c: mm["slope"] for c, mm in measured.items()}, lambda v, k: v * ASSUMED_DEG_FACTOR**k)
            wear = _assume(code, {c: mm["wear"] for c, mm in measured.items() if mm["wear"]},
                           lambda v, k: v * ASSUMED_WEAR_FACTOR**k)
            warm = ref_m["warmup"]
        else:
            continue
        models[code] = CompoundModel(
            code=code,
            label=alloc.label(code),
            color=alloc.color(code),
            offset_s=float(offset),
            deg_s_per_lap=float(deg),
            wear_pct_per_lap=wear,
            warmup_s=float(max(0.0, warm)),
            n_stints=m["n_stints"] if m else 0,
            n_laps=m["n_laps"] if m else 0,
            source=source,
        )

    # A harder compound measured faster than a softer one is almost always fuel / track
    # evolution leaking into the offset (one race, stints at very different fuel loads).
    for code, cm in models.items():
        cm.note = offset_notes.get(code, "")
        for other in models.values():
            if softness(other.code) > softness(code) and cm.offset_s < other.offset_s - 0.05 and cm.source == "measured":
                cm.note = f"Faster than softer {other.label}: likely fuel / track evolution — review the offset."
                break

    return TrackTyreModel(
        track=alloc.track or track,
        state=state,
        base_pace_s=base,
        ref_compound=ref,
        compounds=models,
        pit_losses=pit_losses,
        sc_pit_losses=sc_losses,
        stats=stats,
        fuel_per_lap=float(np.median(fuel)) if fuel else None,
        race_laps_seen=max(race_laps) if race_laps else None,
        allocation=alloc,
        sources=used,
    )


def model_to_json(model: TrackTyreModel) -> str:
    return json.dumps(
        {
            str(c): {"offset_s": m.offset_s, "deg_s_per_lap": m.deg_s_per_lap, "wear_pct_per_lap": m.wear_pct_per_lap, "warmup_s": m.warmup_s}
            for c, m in model.compounds.items()
        }
    )
