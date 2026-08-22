"""
Build a recommended garage setup from practice telemetry.

The engineer starts from the setup you actually ran, diagnoses entry / mid /
exit balance from inputs + tyre temps, then applies a small coordinated
change — not a pile of conflicting wing/ARB clicks.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .corners import normalize_track_name
from .metrics import build_lap_summary, get_lap
from .setup_tweaker import SETUP_PARAMS, estimate_setup_delta, normalize_setup, psi_to_pa
from .track_setups import get_typical_setup

# Live telemetry wheel order in SRT: 0=RL, 1=RR, 2=FL, 3=FR
# Garage setup indices: 0/1 = front, 2/3 = rear
FRONT_PRESS = ("tyre_press_setup_0", "tyre_press_setup_1")
REAR_PRESS = ("tyre_press_setup_2", "tyre_press_setup_3")
FRONT_RH = ("susp_height_setup_0", "susp_height_setup_1")
REAR_RH = ("susp_height_setup_2", "susp_height_setup_3")

# F1 26 working windows (surface temps from practice dumps)
TYRE_HOT = 103.0
TYRE_COLD = 78.0
# Wets / inters run cooler — do not treat ~70°C as "cold slicks"
TYRE_HOT_WET = 88.0
TYRE_COLD_WET = 42.0
TYRE_HOT_INTER = 95.0
TYRE_COLD_INTER = 55.0


@dataclass
class SetupChange:
    key: str
    label: str
    before: float
    after: float
    reason: str


@dataclass
class BuiltSetup:
    setup: dict[str, float]
    base_source: str
    track: str | None
    variant: str
    findings: list[str]
    changes: list[SetupChange] = field(default_factory=list)
    est_dt_vs_session: float | None = None
    est_dt_vs_typical: float | None = None
    diagnosis: str = ""


def _clip(key: str, value: float) -> float:
    for p in SETUP_PARAMS:
        if p.key == key:
            return float(np.clip(value, p.min_v, p.max_v))
    return float(value)


def _label(key: str) -> str:
    for p in SETUP_PARAMS:
        if p.key == key:
            return p.label
    return key


def _apply(setup: dict[str, float], key: str, value: float, reason: str, changes: list[SetupChange]) -> None:
    new_v = _clip(key, value)
    old_v = float(setup[key]) if key in setup else new_v
    setup[key] = new_v
    if abs(new_v - old_v) < 1e-6:
        return
    changes.append(SetupChange(key=key, label=_label(key), before=old_v, after=new_v, reason=reason))


def _nudge(setup: dict[str, float], key: str, delta: float, reason: str, changes: list[SetupChange]) -> None:
    if key not in setup:
        return
    _apply(setup, key, float(setup[key]) + delta, reason, changes)


def _nudge_pair(
    setup: dict[str, float],
    keys: tuple[str, str],
    delta: float,
    reason: str,
    changes: list[SetupChange],
) -> None:
    for k in keys:
        _nudge(setup, k, delta, reason, changes)


def _equalize_pair(setup: dict[str, float], keys: tuple[str, str]) -> None:
    present = [k for k in keys if k in setup]
    if len(present) < 2:
        return
    mid = float(np.mean([setup[k] for k in present]))
    for k in present:
        setup[k] = _clip(k, mid)


def _series(lap_df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col in lap_df.columns:
        return lap_df[col].astype(float)
    return pd.Series(default, index=lap_df.index, dtype=float)


def _axle_temps(df: pd.DataFrame, mask: pd.Series | None = None) -> dict[str, float]:
    cols = [f"tyre_temp_{i}" for i in range(4)]
    if not all(c in df.columns for c in cols):
        return {}
    sl = df.loc[mask] if mask is not None and mask.any() else df
    if sl.empty:
        sl = df
    rl, rr, fl, fr = [float(sl[c].mean()) for c in cols]
    front = (fl + fr) / 2
    rear = (rl + rr) / 2
    return {
        "rl": rl,
        "rr": rr,
        "fl": fl,
        "fr": fr,
        "front": front,
        "rear": rear,
        "spread": front - rear,
        "avg": (front + rear) / 2,
        "left": (rl + fl) / 2,
        "right": (rr + fr) / 2,
        "lr_spread": abs((rl + fl) / 2 - (rr + fr) / 2),
    }


def _phase_masks(lap_df: pd.DataFrame) -> dict[str, pd.Series]:
    g = _series(lap_df, "g_lat").abs()
    thr = _series(lap_df, "throttle")
    brk = _series(lap_df, "brake")
    spd = _series(lap_df, "speed")
    g_cut = max(1.1, float(g.quantile(0.55)) * 0.55) if g.max() > 0.4 else 1.1
    cornering = g > g_cut
    entry = cornering & (brk > 0.12) & (thr < 0.35)
    mid = cornering & (brk < 0.12) & (thr < 0.50)
    exit_ = (thr > 0.45) & (brk < 0.08) & (spd < 210) & (g > 0.5)
    braking = brk > 0.25
    return {"entry": entry, "mid": mid, "exit": exit_, "corner": cornering, "braking": braking}


def _steer_norm(lap_df: pd.DataFrame) -> pd.Series:
    s = _series(lap_df, "steering").abs()
    p98 = float(s.quantile(0.98))
    scale = p98 if p98 > 1e-6 else 1.0
    return (s / scale).clip(0, 1.5)


def _efficiency(lap_df: pd.DataFrame, mask: pd.Series) -> float:
    """Lateral G per unit steering. Low = push / understeer."""
    if not mask.any() or "g_lat" not in lap_df.columns:
        return float("nan")
    g = _series(lap_df, "g_lat").abs()
    sn = _steer_norm(lap_df)
    val = (g / (sn + 0.18)).loc[mask]
    val = val.replace([np.inf, -np.inf], np.nan).dropna()
    return float(val.median()) if len(val) else float("nan")


def _mean_mask(series: pd.Series, mask: pd.Series) -> float:
    if not mask.any():
        return float("nan")
    sl = series.loc[mask].astype(float)
    return float(sl.mean()) if len(sl) else float("nan")


def _strength(score: float, mild: float, strong: float) -> str:
    a = abs(score)
    if a >= strong:
        return "strong"
    if a >= mild:
        return "medium"
    return "mild"


def analyze_practice_balance(df: pd.DataFrame, lap: int | None = None) -> dict[str, Any]:
    """Derive entry / mid / exit balance from a push lap."""
    summary = build_lap_summary(df)
    if summary.empty:
        return {}
    if lap is None:
        lap = int(summary.loc[summary["is_best"], "lap"].iloc[0])
    lap_df = get_lap(df, int(lap))
    if lap_df.empty:
        return {}

    out: dict[str, Any] = {
        "lap": int(lap),
        "lap_time": float(summary.loc[summary["lap"] == lap, "lap_time"].iloc[0]),
    }

    masks = _phase_masks(lap_df)
    temps_all = _axle_temps(lap_df)
    temps_c = _axle_temps(lap_df, masks["corner"])
    if temps_c:
        out.update(
            {
                "temp_front": temps_c["front"],
                "temp_rear": temps_c["rear"],
                "temp_spread_axle": temps_c["spread"],
                "temp_avg": temps_c["avg"],
                "temp_lr_spread": temps_c["lr_spread"],
            }
        )
    elif temps_all:
        out["temp_front"] = temps_all["front"]
        out["temp_rear"] = temps_all["rear"]
        out["temp_spread_axle"] = temps_all["spread"]
        out["temp_avg"] = temps_all["avg"]

    slip = _series(lap_df, "slip_max")
    out["entry_eff"] = _efficiency(lap_df, masks["entry"])
    out["mid_eff"] = _efficiency(lap_df, masks["mid"])
    out["exit_slip"] = _mean_mask(slip, masks["exit"])
    out["entry_slip"] = _mean_mask(slip, masks["entry"])
    out["mid_slip"] = _mean_mask(slip, masks["mid"])

    if masks["braking"].any() and "lockup_risk" in lap_df.columns:
        brk = masks["braking"]
        out["lockup_frac"] = float(lap_df.loc[brk, "lockup_risk"].astype(float).mean())
        out["lockups"] = int(lap_df["lockup_risk"].sum())
        if "lockup_front" in lap_df.columns:
            out["lockup_front_frac"] = float(lap_df.loc[brk, "lockup_front"].astype(float).mean())
        if "lockup_rear" in lap_df.columns:
            out["lockup_rear_frac"] = float(lap_df.loc[brk, "lockup_rear"].astype(float).mean())
    elif "lockup_risk" in lap_df.columns:
        out["lockups"] = int(lap_df["lockup_risk"].sum())
        out["lockup_frac"] = 0.0

    if "throttle" in lap_df.columns:
        out["wot_pct"] = float((lap_df["throttle"] > 0.98).mean() * 100)
    if "coasting" in lap_df.columns:
        out["coast_pct"] = float(lap_df["coasting"].mean() * 100)

    # Signed balance: + understeer, − oversteer. Blend efficiency, temps, slip.
    # Efficiency is track-relative: compare mid vs entry, and vs this lap's corner median.
    corner_eff = _efficiency(lap_df, masks["corner"])
    mid_eff = out["mid_eff"]
    entry_eff = out["entry_eff"]
    spread = float(out.get("temp_spread_axle") or 0.0)
    exit_slip = out.get("exit_slip")
    entry_slip = out.get("entry_slip")

    entry_score = 0.0
    mid_score = 0.0
    exit_score = 0.0

    if np.isfinite(entry_eff) and np.isfinite(corner_eff):
        # Lower than the lap's own corner efficiency → push on entry
        entry_score += float(np.clip((corner_eff - entry_eff) / max(abs(corner_eff), 0.4), -1.5, 1.5))
    if np.isfinite(mid_eff) and np.isfinite(corner_eff):
        mid_score += float(np.clip((corner_eff - mid_eff) / max(abs(corner_eff), 0.4), -1.5, 1.5))

    # Fronts hotter than rears in corners → fronts working / sliding (understeer)
    # Rears hotter → rear limited (oversteer / traction)
    entry_score += float(np.clip(spread / 12.0, -1.2, 1.2)) * 0.55
    mid_score += float(np.clip(spread / 12.0, -1.2, 1.2)) * 0.70

    if exit_slip is not None and np.isfinite(exit_slip):
        # High driven slip → oversteer / traction (negative)
        exit_score -= float(np.clip((exit_slip - 0.045) / 0.06, -0.3, 1.8))
    if spread < -5:
        exit_score -= float(np.clip((-spread - 5) / 10.0, 0, 1.2))
    if entry_slip is not None and np.isfinite(entry_slip) and entry_slip > 0.07:
        # Front lock / slide on entry often reads as understeer if fronts are hotter
        if spread >= 0:
            entry_score += 0.35
        else:
            entry_score -= 0.35

    out["entry_score"] = float(entry_score)
    out["mid_score"] = float(mid_score)
    out["exit_score"] = float(exit_score)

    # Dominant story
    ranked = sorted(
        (("entry", entry_score), ("mid", mid_score), ("exit", exit_score)),
        key=lambda x: abs(x[1]),
        reverse=True,
    )
    phase, score = ranked[0]
    if abs(score) < 0.28 and abs(ranked[1][1]) < 0.28:
        out["issue"] = "balanced"
        out["issue_phase"] = "all"
        out["issue_strength"] = "none"
    else:
        kind = "understeer" if score > 0 else "oversteer"
        # Mixed: entry push + exit snap is common
        if entry_score > 0.35 and exit_score < -0.35:
            out["issue"] = "mixed"
            out["issue_phase"] = "entry+exit"
            out["issue_strength"] = _strength(max(abs(entry_score), abs(exit_score)), 0.45, 0.85)
        else:
            out["issue"] = kind
            out["issue_phase"] = phase
            out["issue_strength"] = _strength(score, 0.45, 0.90)

    if "fuel_used" in summary.columns:
        out["fuel_median"] = float(summary["fuel_used"].median())
        out["fuel_best"] = float(summary.loc[summary["lap"] == lap, "fuel_used"].iloc[0])
    return out


def _delta_for_strength(strength: str, mild: float, medium: float, strong: float) -> float:
    return {"mild": mild, "medium": medium, "strong": strong}.get(strength, medium)


def _apply_understeer(setup: dict[str, float], phase: str, strength: str, changes: list[SetupChange], findings: list[str]) -> None:
    w = _delta_for_strength(strength, 1, 2, 2)
    # One ARB click max — stacking soft-front + stiff-rear on a wild base = snap oversteer
    arb = 1
    diff = _delta_for_strength(strength, 0.01, 0.02, 0.03)
    findings.append(
        f"{strength.capitalize()} {phase} understeer — prefer front wing; keep springs/ARBs matched."
    )
    if phase in ("entry", "all"):
        _nudge(setup, "diff_offThrottle_setup", -diff, "Slightly freer off-throttle for entry rotation", changes)
        _nudge(setup, "toe_setup_0", 0.01, "A touch more front toe-out for turn-in", changes)
    if phase in ("mid", "all", "entry"):
        _nudge(setup, "wing_setup_0", w, "More front wing vs push", changes)
        af = setup.get("arb_setup_0")
        ar = setup.get("arb_setup_1")
        # Soften front ARB only if it stays within 3 of rear (don't create split packages)
        if af is not None and (ar is None or af - 1 >= (ar or af) - 3):
            _nudge(setup, "arb_setup_0", -arb, "Softer front ARB for mid-corner rotation", changes)
        if strength != "mild":
            _nudge(setup, "camber_setup_0", -0.05, "More negative front camber for mid-corner grip", changes)
    if strength == "strong" and phase == "mid":
        _nudge_pair(setup, FRONT_RH, -1, "Lower front ride height for more front aero", changes)


def _apply_oversteer(setup: dict[str, float], phase: str, strength: str, changes: list[SetupChange], findings: list[str]) -> None:
    w = _delta_for_strength(strength, 1, 2, 2)
    diff = _delta_for_strength(strength, 0.04, 0.06, 0.08)
    findings.append(
        f"{strength.capitalize()} {phase} oversteer — plant the rear with wing/diff; don't flop the rear spring."
    )
    if phase in ("exit", "all"):
        _nudge(setup, "diff_onThrottle_setup", diff, "Tighter on-throttle diff to calm exits", changes)
        ar = setup.get("arb_setup_1")
        af = setup.get("arb_setup_0")
        if ar is not None and ar >= 8 and (af is None or ar - 1 <= (af or ar) + 3):
            _nudge(setup, "arb_setup_1", -1, "Slightly softer rear ARB for traction", changes)
        sr = setup.get("susp_spring_setup_1")
        # Only ease rear spring if it's already on the firm side — never toward 3–8
        if strength != "mild" and sr is not None and sr >= 16:
            _nudge(setup, "susp_spring_setup_1", -1, "Slightly softer rear spring for exit grip", changes)
        if strength != "mild":
            _nudge(setup, "camber_setup_1", 0.05, "Less rear camber to help traction", changes)
    if phase in ("mid", "entry", "all"):
        _nudge(setup, "wing_setup_1", w, "More rear wing for stability", changes)
        if phase == "entry":
            _nudge(setup, "diff_offThrottle_setup", diff, "Tighter off-throttle diff for entry stability", changes)
            _nudge(setup, "toe_setup_1", 0.02, "More rear toe-in for stability", changes)
            _nudge(setup, "brake_bias_setup", 0.01, "Forward bias — stop rear locking on entry", changes)
    if strength == "strong" and phase == "exit":
        _nudge_pair(setup, REAR_PRESS, -psi_to_pa(0.3), "A little less rear pressure for mechanical grip", changes)


def _apply_mixed(setup: dict[str, float], strength: str, changes: list[SetupChange], findings: list[str]) -> None:
    findings.append(
        "Push on entry and loose on exit — fix with aero/diff; leave spring package matched."
    )
    diff_off = _delta_for_strength(strength, 0.01, 0.02, 0.03)
    diff_on = _delta_for_strength(strength, 0.05, 0.08, 0.10)
    _nudge(setup, "diff_offThrottle_setup", -diff_off, "Slightly freer off-throttle for entry", changes)
    _nudge(setup, "diff_onThrottle_setup", diff_on, "Tighter on-throttle to stop exit snap", changes)
    _nudge(setup, "brake_bias_setup", 0.01, "Slight forward bias for stable brake entry", changes)
    if strength != "mild":
        _nudge(setup, "wing_setup_1", 1, "One click of rear wing for exit stability", changes)
        _nudge(setup, "toe_setup_0", 0.01, "A little front toe-out for turn-in", changes)
        # Soften rear ARB one click only if matched package allows
        ar = setup.get("arb_setup_1")
        af = setup.get("arb_setup_0")
        if ar is not None and ar >= 8 and (af is None or abs((af or ar) - (ar - 1)) <= 3):
            _nudge(setup, "arb_setup_1", -1, "Slightly softer rear ARB for traction", changes)


def _harmonize_mech(
    setup: dict[str, float],
    changes: list[SetupChange],
    findings: list[str],
) -> None:
    """Clamp spring/ARB into a coherent package after coach nudges."""
    from .track_setups import coherent_suspension

    need = ("susp_spring_setup_0", "susp_spring_setup_1", "arb_setup_0", "arb_setup_1")
    if not all(k in setup for k in need):
        return
    sf0, sr0 = float(setup["susp_spring_setup_0"]), float(setup["susp_spring_setup_1"])
    af0, ar0 = float(setup["arb_setup_0"]), float(setup["arb_setup_1"])
    sf, sr, af, ar = coherent_suspension(sf0, sr0, af0, ar0)
    touched = False
    for key, old, new in (
        ("susp_spring_setup_0", sf0, sf),
        ("susp_spring_setup_1", sr0, sr),
        ("arb_setup_0", af0, af),
        ("arb_setup_1", ar0, ar),
    ):
        if abs(old - new) >= 0.5:
            _apply(setup, key, new, "Harmonise suspension — keep F/R package matched", changes)
            touched = True
    if touched:
        findings.append(
            f"Suspension harmonised to springs {sf:.0f}/{sr:.0f} · ARB {af:.0f}/{ar:.0f} "
            "(avoids front-stiff / rear-floppy snap)."
        )


def _tyre_thresholds(conditions: str | None) -> tuple[float, float]:
    from .conditions import _as_state

    state = _as_state(conditions)
    if state == "wet":
        return TYRE_HOT_WET, TYRE_COLD_WET
    if state in ("inter", "damp"):
        return TYRE_HOT_INTER, TYRE_COLD_INTER
    return TYRE_HOT, TYRE_COLD


def _tyre_window(
    setup: dict[str, float],
    symptoms: dict[str, Any],
    changes: list[SetupChange],
    findings: list[str],
    conditions: str | None = None,
) -> None:
    from .conditions import STATE_LABELS, _as_state, is_wet_surface

    tavg = symptoms.get("temp_avg")
    spread = symptoms.get("temp_spread_axle")
    if tavg is None:
        return
    hot, cold = _tyre_thresholds(conditions)
    bump = psi_to_pa(0.3 if is_wet_surface(conditions) else 0.4)
    state = _as_state(conditions)
    if tavg > hot:
        findings.append(
            f"Tyres hot in corners ({tavg:.0f}°C, {STATE_LABELS[state]} window) — raise pressures on the working axle."
        )
        if spread is not None and spread > 6:
            _nudge_pair(setup, FRONT_PRESS, bump, "Fronts overheating — raise psi", changes)
        elif spread is not None and spread < -6:
            _nudge_pair(setup, REAR_PRESS, bump, "Rears overheating — raise psi", changes)
        else:
            _nudge_pair(setup, FRONT_PRESS, bump, "Hot tyres — raise front psi", changes)
            _nudge_pair(setup, REAR_PRESS, bump, "Hot tyres — raise rear psi", changes)
    elif tavg < cold:
        if is_wet_surface(conditions):
            findings.append(
                f"Surface temps low ({tavg:.0f}°C) — expected in {STATE_LABELS[state]}; "
                "avoid big pressure cuts that overheat the carcass later."
            )
            if tavg < cold - 8:
                _nudge_pair(setup, FRONT_PRESS, -bump * 0.5, "Very cold wet/inter — slight −psi fronts", changes)
                _nudge_pair(setup, REAR_PRESS, -bump * 0.5, "Very cold wet/inter — slight −psi rears", changes)
        else:
            findings.append(f"Tyres cool in corners ({tavg:.0f}°C) — drop pressures to help warm-up.")
            _nudge_pair(setup, FRONT_PRESS, -bump, "Cold tyres — −0.4 psi fronts", changes)
            _nudge_pair(setup, REAR_PRESS, -bump, "Cold tyres — −0.4 psi rears", changes)


def _brake_fix(
    setup: dict[str, float],
    symptoms: dict[str, Any],
    changes: list[SetupChange],
    findings: list[str],
    conditions: str | None = None,
) -> None:
    """
    Fix brake bite / bias without spinning the car.

    'Touch of brake = wall' is almost always too much initial pressure and/or
    bias too far rearward (rear locks, car rotates into the barrier). Old logic
    always moved bias rearward on any lockup — that made rear snaps worse.
    """
    from .conditions import is_wet_surface

    frac = float(symptoms.get("lockup_frac") or 0.0)
    front_f = symptoms.get("lockup_front_frac")
    rear_f = symptoms.get("lockup_rear_frac")
    spread = float(symptoms.get("temp_spread_axle") or 0.0)
    issue = symptoms.get("issue") or "balanced"
    phase = symptoms.get("issue_phase") or "all"

    # Always soften absurd 100% pressure a touch on coach builds — safer bite
    press = setup.get("brake_press_setup")
    if press is not None and press > 0.97 and (frac >= 0.05 or issue == "oversteer"):
        _nudge(setup, "brake_press_setup", -0.03, "Ease brake pressure — softer initial bite", changes)
        findings.append("Brake pressure was near max — eased for controllable initial bite.")

    if frac >= 0.06 or front_f is not None or rear_f is not None:
        rear_dom = False
        front_dom = False
        if front_f is not None and rear_f is not None:
            rear_dom = rear_f >= front_f + 0.02 and rear_f >= 0.05
            front_dom = front_f >= rear_f + 0.02 and front_f >= 0.05
        else:
            # No axle split: use balance clues. Entry oversteer / hot rears → treat as rear lock.
            if issue == "oversteer" and phase in ("entry", "all", "mid"):
                rear_dom = True
            elif spread < -4:
                rear_dom = True
            elif spread > 5 and frac >= 0.08:
                front_dom = True
            elif frac >= 0.12:
                # Ambiguous lockups: prefer safer forward bias + lower pressure, not rearward
                rear_dom = True

        if rear_dom or (frac >= 0.10 and not front_dom):
            findings.append(
                "Rear locking / unstable on the brakes — move bias forward and soften pressure so light inputs don't spin you."
            )
            _nudge(setup, "brake_bias_setup", 0.02 if frac >= 0.14 else 0.01, "Forward bias vs rear lock / entry snap", changes)
            _nudge(setup, "brake_press_setup", -0.03 if frac >= 0.14 else -0.02, "Lower brake pressure for gentler bite", changes)
            if setup.get("diff_offThrottle_setup") is not None:
                _nudge(setup, "diff_offThrottle_setup", 0.03, "Tighter off-throttle while braking", changes)
        elif front_dom:
            findings.append(
                f"Front lock-ups (~{frac * 100:.0f}% of heavy brake) — small rearward bias and/or less pressure."
            )
            # Only 1% rearward max — large rearward moves cause the wall snap
            _nudge(setup, "brake_bias_setup", -0.01, "Slight rearward bias vs front lock-ups", changes)
            if frac >= 0.14:
                _nudge(setup, "brake_press_setup", -0.02, "Ease brake pressure — front lock-ups", changes)
        elif frac >= 0.08:
            findings.append("Lock-ups under braking — ease pressure first (safer than big bias swings).")
            _nudge(setup, "brake_press_setup", -0.02, "Ease brake pressure vs lock-ups", changes)

    _clamp_brake_stability(setup, changes, findings, conditions=conditions)


def _clamp_brake_stability(
    setup: dict[str, float],
    changes: list[SetupChange],
    findings: list[str],
    conditions: str | None = None,
) -> None:
    """Hard safety band so coach never ships a spin-prone brake package."""
    from .conditions import is_wet_surface

    wet = is_wet_surface(conditions)
    # Dry: keep bias forward enough to be driveable. Wet: allow a touch more rear.
    lo, hi = (0.53, 0.62) if wet else (0.55, 0.62)
    bias_key = "brake_bias_setup" if "brake_bias_setup" in setup else None
    if bias_key:
        cur = float(setup[bias_key])
        clipped = float(np.clip(cur, lo, hi))
        if abs(clipped - cur) > 1e-6:
            _apply(
                setup,
                bias_key,
                clipped,
                f"Clamp bias to safe band ({lo * 100:.0f}–{hi * 100:.0f}% front)",
                changes,
            )
            findings.append(
                f"Brake bias clamped to {clipped * 100:.0f}% front — outside this range the car snaps on light brake."
            )
        if "front_brake_bias" in setup:
            setup["front_brake_bias"] = setup[bias_key]

    if "brake_press_setup" in setup:
        press = float(setup["brake_press_setup"])
        # Cap bite unless the driver is clearly locking only the fronts with low pressure
        max_press = 0.97 if wet else 0.98
        if press > max_press:
            _apply(setup, "brake_press_setup", max_press, "Cap brake pressure for controllable bite", changes)



def _aero_vs_typical(
    setup: dict[str, float],
    typical: dict[str, Any] | None,
    symptoms: dict[str, Any],
    changes: list[SetupChange],
    findings: list[str],
) -> None:
    """Only nudge wings toward the track pack if balance is already OK."""
    if not typical or symptoms.get("issue") not in ("balanced",):
        return
    tsetup = typical["setup"]
    character = typical.get("character") or ""
    wot = symptoms.get("wot_pct") or 0.0
    fw = setup.get("wing_setup_0")
    rw = setup.get("wing_setup_1")
    tfw = tsetup.get("wing_setup_0")
    trw = tsetup.get("wing_setup_1")
    if fw is None or rw is None or tfw is None or trw is None:
        return
    # Power tracks: if you're carrying extra rear wing vs typical, trim it
    if character in ("low_drag", "medium_low") and wot > 52 and rw > trw + 2:
        _nudge(setup, "wing_setup_1", -min(2, rw - trw), "High full-throttle share — trim rear wing toward the track pack", changes)
        findings.append(f"Lap is {wot:.0f}% full throttle on a power-sensitive track — rear wing was high vs typical.")
        return
    # High DF tracks: if you're a long way below typical and balanced, add a little
    if character in ("high_df",) and (tfw - fw) >= 6:
        _nudge(setup, "wing_setup_0", 2, "Wings low vs high-DF typical — add front wing", changes)
        _nudge(setup, "wing_setup_1", 2, "Wings low vs high-DF typical — add rear wing", changes)
        findings.append("Balance is OK but downforce is low vs the track pack — added two clicks each.")


def _change_group(key: str, reason: str) -> str:
    r = reason.lower()
    if key in ("brake_bias_setup", "front_brake_bias", "brake_press_setup"):
        return "brakes"
    if "brake" in r or "bias" in r or "lock" in r or "bite" in r:
        return "brakes"
    if key.startswith("wing"):
        return "aero"
    if key.startswith("tyre_press"):
        return "tyres"
    if key.startswith("diff"):
        return "diff"
    if key.startswith(("arb", "susp_", "camber", "toe")):
        return "mech"
    return "other"


def _enforce_change_budget(changes: list[SetupChange], max_groups: int = 3) -> list[SetupChange]:
    """
    Keep at most max_groups mechanical lever groups (+ fuel always kept).

    Order: brakes → aero OR mech (not both) → diff OR tyres.
    """
    fuel = [c for c in changes if c.key == "fuel_setup"]
    mech = [c for c in changes if c.key != "fuel_setup"]
    if not mech:
        return fuel

    groups: dict[str, list[SetupChange]] = {}
    for c in mech:
        g = _change_group(c.key, c.reason)
        groups.setdefault(g, []).append(c)

    order = ["brakes", "aero", "mech", "diff", "tyres", "other"]
    kept: list[SetupChange] = []
    used: set[str] = set()

    for g in order:
        if g not in groups:
            continue
        if g == "mech" and "aero" in used:
            continue
        if g == "aero" and "mech" in used:
            continue
        if len(used) >= max_groups:
            break
        used.add(g)
        kept.extend(groups[g])

    return fuel + kept


def _reapply_changes(setup: dict[str, float], changes: list[SetupChange]) -> None:
    for c in changes:
        setup[c.key] = _clip(c.key, c.after)
        if c.key == "brake_bias_setup" and "front_brake_bias" in setup:
            setup["front_brake_bias"] = setup[c.key]


def _guard_track_wings(
    setup: dict[str, float],
    typical: dict[str, Any] | None,
    changes: list[SetupChange],
    findings: list[str],
) -> None:
    """Never ship zero/min wings on high-DF circuits (Monaco, etc.)."""
    if not typical:
        return
    char = str(typical.get("character") or "")
    if char not in ("high_df", "medium_high"):
        return
    ts = typical.get("setup") or {}
    floors = {
        "wing_setup_0": max(0.0, float(ts.get("wing_setup_0", 40)) - 8),
        "wing_setup_1": max(0.0, float(ts.get("wing_setup_1", 40)) - 8),
    }
    for key, floor in floors.items():
        if key not in setup:
            continue
        cur = float(setup[key])
        if cur >= floor:
            continue
        _apply(
            setup,
            key,
            floor,
            f"Floor {key.replace('_setup', '').replace('_', ' ')} for {typical.get('track', 'this track')} high-DF pack",
            changes,
        )
        findings.append(
            f"Wing read as {cur:.0f} in export — raised to {floor:.0f} for a high-downforce track."
        )


def build_setup_from_practice(
    df: pd.DataFrame,
    session_setup: dict[str, Any] | None,
    track: str | None,
    *,
    variant: str = "quali",
    lap: int | None = None,
    prefer_typical_base: bool = False,
    conditions: str | None = None,
    diagnosis: Any | None = None,
    corner_cmp: pd.DataFrame | None = None,
) -> BuiltSetup:
    """
    Start from the session garage (what you ran), fill missing keys from the
    track typical, then apply a small diagnosis-led tweak.
    """
    from .conditions import STATE_LABELS, _as_state, is_wet_surface, weather_banner
    from .loader import repair_setup_from_telemetry
    from .track_setups import apply_weather_overlay

    track_n = normalize_track_name(track)
    state = _as_state(conditions)
    typical = get_typical_setup(track_n, variant, conditions=state)
    typical_setup = (typical or {}).get("setup")
    session_n = repair_setup_from_telemetry(
        session_setup,
        df,
        lap,
        typical_setup=typical_setup,
    )

    if prefer_typical_base and typical:
        setup = deepcopy(typical["setup"])
        base_source = f"Typical {track_n} {typical['variant']} ({STATE_LABELS[state]})"
        findings = [typical["notes"], "Started from the track typical (not your session garage)."]
    elif session_n:
        setup = deepcopy(session_n)
        if is_wet_surface(state):
            # Session garage is usually a dry export — bias keys toward wet typical
            setup = apply_weather_overlay(setup, state)
            base_source = f"Your session setup + {STATE_LABELS[state]} overlay"
            findings = [
                f"Started from the session garage, then applied the {STATE_LABELS[state]} weather overlay."
            ]
        else:
            base_source = "Your session setup"
            findings = ["Started from the setup stored in this practice export."]
    elif typical:
        setup = deepcopy(typical["setup"])
        base_source = f"Typical {track_n} {typical['variant']} ({STATE_LABELS[state]})"
        findings = [typical["notes"], "No session garage — used the track typical as a starting point."]
    else:
        setup = deepcopy(_fallback_setup())
        if is_wet_surface(state):
            setup = apply_weather_overlay(setup, state)
        base_source = f"Generic baseline ({STATE_LABELS[state]})"
        findings = ["No track typical or session setup — used a generic F1 26 baseline."]

    banner = weather_banner(state)
    if banner:
        findings.insert(0, banner)

    if typical:
        for k, v in typical["setup"].items():
            setup.setdefault(k, v)
    for k, v in session_n.items():
        if not is_wet_surface(state):
            setup.setdefault(k, v)

    changes: list[SetupChange] = []
    lap_diag = diagnosis
    symptoms = analyze_practice_balance(df, lap=lap)
    if lap_diag is not None and lap_diag.symptoms:
        symptoms = lap_diag.symptoms
    elif lap_diag is None and symptoms:
        from .diagnosis import build_lap_diagnosis

        lap_diag = build_lap_diagnosis(
            df,
            int(symptoms["lap"]),
            ref_lap=None,
            corner_cmp=corner_cmp,
            conditions=conditions,
            track=track,
        )

    if not symptoms:
        return BuiltSetup(
            setup=setup,
            base_source=base_source,
            track=track_n,
            variant=variant,
            findings=findings + ["Not enough lap data to refine further."],
            changes=changes,
            diagnosis="none",
        )

    setup_before_changes = deepcopy(setup)

    findings.append(f"Tuned from practice lap {symptoms['lap']} ({symptoms['lap_time']:.3f}s).")
    if lap_diag is not None:
        findings.append(f"Engineer read: {lap_diag.headline}")
    if symptoms.get("temp_avg") is not None:
        findings.append(
            f"Corner tyre temps F {symptoms.get('temp_front', 0):.0f}°C / R {symptoms.get('temp_rear', 0):.0f}°C "
            f"(Δ {symptoms.get('temp_spread_axle', 0):+.0f}°C)."
        )

    issue = symptoms.get("issue", "balanced")
    phase = symptoms.get("issue_phase", "all")
    strength = symptoms.get("issue_strength", "mild")
    diag_label = f"{issue} ({phase}, {strength})" if issue != "balanced" else "balanced"

    _brake_fix(setup, symptoms, changes, findings, conditions=state)

    if issue == "understeer":
        _apply_understeer(setup, phase, strength, changes, findings)
    elif issue == "oversteer":
        _apply_oversteer(setup, phase, strength, changes, findings)
    elif issue == "mixed":
        _apply_mixed(setup, strength, changes, findings)
    else:
        findings.append("Balance looks even — no big aero/ARB swing.")
        # Dry aero vs typical is misleading on a wet surface
        if not is_wet_surface(state):
            _aero_vs_typical(setup, typical, symptoms, changes, findings)
        elif typical:
            findings.append(f"{STATE_LABELS[state]}: keeping weather-oriented wing/ARB targets.")

    _tyre_window(setup, symptoms, changes, findings, conditions=state)

    if variant == "race" and typical:
        _apply(setup, "fuel_setup", typical["setup"]["fuel_setup"], "Race fuel from track typical", changes)
    elif variant == "quali":
        _apply(setup, "fuel_setup", 5.0, "Quali fuel — garage minimum (5 kg)", changes)

    pre_n = len([c for c in changes if c.key != "fuel_setup"])
    changes = _enforce_change_budget(changes, max_groups=3)
    post_n = len([c for c in changes if c.key != "fuel_setup"])
    if post_n < pre_n:
        setup = deepcopy(setup_before_changes)
        _reapply_changes(setup, changes)
        findings.append(
            f"Kept {post_n} coordinated garage move(s) — brakes first, then one aero/mech lever, then diff/tyres."
        )

    # Final safety net after budget trim
    _harmonize_mech(setup, changes, findings)
    _clamp_brake_stability(setup, changes, findings, conditions=state)
    _guard_track_wings(setup, typical, changes, findings)

    if "brake_bias_setup" in setup and "front_brake_bias" in setup:
        setup["front_brake_bias"] = setup["brake_bias_setup"]

    for pair in (FRONT_PRESS, REAR_PRESS, FRONT_RH, REAR_RH):
        _equalize_pair(setup, pair)

    est_session = (
        estimate_setup_delta(session_n, setup, track=track_n, conditions=state).total_dt if session_n else None
    )
    est_typical = (
        estimate_setup_delta(typical["setup"], setup, track=track_n, conditions=state).total_dt if typical else None
    )

    mech = [c for c in changes if c.key != "fuel_setup"]
    if not mech:
        findings.append("No garage change beyond fuel — the lap didn't show a clear setup issue.")

    return BuiltSetup(
        setup=setup,
        base_source=base_source,
        track=track_n,
        variant=variant,
        findings=findings,
        changes=changes,
        est_dt_vs_session=est_session,
        est_dt_vs_typical=est_typical,
        diagnosis=diag_label,
    )


def _fallback_setup() -> dict[str, float]:
    return {
        "fuel_setup": 5.0,
        "wing_setup_0": 30.0,
        "wing_setup_1": 25.0,
        "diff_onThrottle_setup": 0.65,
        "diff_offThrottle_setup": 0.35,
        "camber_setup_0": -3.50,
        "camber_setup_1": -2.00,
        "toe_setup_0": 0.05,
        "toe_setup_1": 0.13,
        "susp_spring_setup_0": 37.0,
        "susp_spring_setup_1": 17.0,
        "arb_setup_0": 10.0,
        "arb_setup_1": 10.0,
        "susp_height_setup_0": 21.0,
        "susp_height_setup_1": 21.0,
        "susp_height_setup_2": 45.0,
        "susp_height_setup_3": 45.0,
        "brake_bias_setup": 0.57,
        "front_brake_bias": 0.57,
        "brake_press_setup": 0.95,
        "tyre_press_setup_0": psi_to_pa(26.5),
        "tyre_press_setup_1": psi_to_pa(26.5),
        "tyre_press_setup_2": psi_to_pa(23.5),
        "tyre_press_setup_3": psi_to_pa(23.5),
    }


def changes_frame(built: BuiltSetup) -> pd.DataFrame:
    if not built.changes:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "Parameter": c.label,
                "Before": c.before,
                "After": c.after,
                "Delta": c.after - c.before,
                "Reason": c.reason,
            }
            for c in built.changes
        ]
    )
