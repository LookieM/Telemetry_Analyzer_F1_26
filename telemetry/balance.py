"""Practice lap balance analysis — entry / mid / exit understeer vs oversteer."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .metrics import build_lap_summary, get_lap


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
    fl, fr, rl, rr = [float(sl[c].mean()) for c in cols]  # export order is front-first
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
        entry_score += float(np.clip((corner_eff - entry_eff) / max(abs(corner_eff), 0.4), -1.5, 1.5))
    if np.isfinite(mid_eff) and np.isfinite(corner_eff):
        mid_score += float(np.clip((corner_eff - mid_eff) / max(abs(corner_eff), 0.4), -1.5, 1.5))

    entry_score += float(np.clip(spread / 12.0, -1.2, 1.2)) * 0.55
    mid_score += float(np.clip(spread / 12.0, -1.2, 1.2)) * 0.70

    if exit_slip is not None and np.isfinite(exit_slip):
        exit_score -= float(np.clip((exit_slip - 0.045) / 0.06, -0.3, 1.8))
    if spread < -5:
        exit_score -= float(np.clip((-spread - 5) / 10.0, 0, 1.2))
    if entry_slip is not None and np.isfinite(entry_slip) and entry_slip > 0.07:
        if spread >= 0:
            entry_score += 0.35
        else:
            entry_score -= 0.35

    out["entry_score"] = float(entry_score)
    out["mid_score"] = float(mid_score)
    out["exit_score"] = float(exit_score)

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
