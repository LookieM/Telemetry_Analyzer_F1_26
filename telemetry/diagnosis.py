"""Shared lap diagnosis for coach + setup engineer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .conditions import STATE_LABELS, _as_state, weather_banner
from .corner_engineer import corner_engineer_callouts
from .metrics import build_lap_summary, get_lap


@dataclass
class LapDiagnosis:
    focus_lap: int
    ref_lap: int | None
    lap_time: float | None
    ref_time: float | None
    time_loss_s: float
    primary_issue: str  # understeer | oversteer | mixed | balanced
    phase: str  # entry | mid | exit | all | entry+exit
    strength: str  # none | mild | medium | strong
    worst_corner: str | None
    worst_corner_loss_s: float
    confidence: float
    track_state: str
    headline: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def symptoms(self) -> dict[str, Any]:
        """Balance dict compatible with setup_builder."""
        return dict(self.evidence.get("balance") or {})


def _headline(d: LapDiagnosis) -> str:
    parts: list[str] = []
    if d.time_loss_s > 0.05 and d.ref_lap is not None:
        parts.append(f"+{d.time_loss_s:.3f}s vs L{d.ref_lap}")
    elif d.ref_lap is None:
        parts.append(f"Lap {d.focus_lap} analysis")
    else:
        parts.append(f"Matched or beat L{d.ref_lap}")

    if d.worst_corner and d.worst_corner_loss_s >= 0.03:
        parts.append(f"biggest loss {d.worst_corner} (+{d.worst_corner_loss_s:.3f}s)")

    if d.primary_issue != "balanced":
        parts.append(f"{d.primary_issue} ({d.phase}, {d.strength})")
    elif not parts:
        parts.append("Balance looks even — look for small technique wins")

    wx = STATE_LABELS.get(d.track_state, "")
    if wx and d.track_state != "dry":
        parts.append(wx.lower())
    return " · ".join(parts)


def build_lap_diagnosis(
    df: pd.DataFrame,
    focus_lap: int,
    *,
    ref_lap: int | None = None,
    corner_cmp: pd.DataFrame | None = None,
    conditions: str | None = None,
    track: str | None = None,
    track_length: float | None = None,
) -> LapDiagnosis:
    """One diagnosis object for coach feed and setup builder."""
    from .setup_builder import analyze_practice_balance

    state = _as_state(conditions)
    summary = build_lap_summary(df, track_length=track_length)
    balance = analyze_practice_balance(df, lap=focus_lap) or {}

    lap_time = balance.get("lap_time")
    if lap_time is None and not summary.empty and focus_lap in summary["lap"].values:
        lap_time = float(summary.loc[summary["lap"] == focus_lap, "lap_time"].iloc[0])

    ref_time = None
    time_loss = 0.0
    if ref_lap is not None and not summary.empty and ref_lap in summary["lap"].values:
        ref_time = float(summary.loc[summary["lap"] == ref_lap, "lap_time"].iloc[0])
        if lap_time is not None:
            time_loss = float(lap_time) - float(ref_time)

    worst_corner = None
    worst_loss = 0.0
    if corner_cmp is not None and not corner_cmp.empty and "delta_s" in corner_cmp.columns:
        timed = corner_cmp[corner_cmp["delta_s"].notna() & (corner_cmp["delta_s"] > 0)]
        if not timed.empty:
            row = timed.sort_values("delta_s", ascending=False).iloc[0]
            worst_corner = str(row.get("corner_name") or row.get("corner_id") or "")
            worst_loss = float(row["delta_s"])

    issue = str(balance.get("issue") or "balanced")
    phase = str(balance.get("issue_phase") or "all")
    strength = str(balance.get("issue_strength") or "none")

    # Confidence: channels + vs-ref + corner data
    conf = 0.45
    lap_df = get_lap(df, focus_lap)
    if len(lap_df) > 400:
        conf += 0.15
    if ref_lap is not None and ref_lap != focus_lap:
        conf += 0.20
    if worst_loss >= 0.05:
        conf += 0.10
    if balance.get("temp_avg") is not None:
        conf += 0.05
    if issue != "balanced":
        conf += 0.05
    conf = float(min(1.0, conf))

    callouts = corner_engineer_callouts(corner_cmp, top_n=1) if corner_cmp is not None else []

    evidence: dict[str, Any] = {
        "balance": balance,
        "lockup_frac": balance.get("lockup_frac"),
        "lockup_front_frac": balance.get("lockup_front_frac"),
        "lockup_rear_frac": balance.get("lockup_rear_frac"),
        "coast_pct": balance.get("coast_pct"),
        "wot_pct": balance.get("wot_pct"),
        "temp_spread_axle": balance.get("temp_spread_axle"),
        "temp_avg": balance.get("temp_avg"),
        "weather_banner": weather_banner(state),
        "top_corner_callout": callouts[0].sentence if callouts else None,
    }

    diag = LapDiagnosis(
        focus_lap=int(focus_lap),
        ref_lap=int(ref_lap) if ref_lap is not None else None,
        lap_time=float(lap_time) if lap_time is not None else None,
        ref_time=float(ref_time) if ref_time is not None else None,
        time_loss_s=float(time_loss),
        primary_issue=issue,
        phase=phase,
        strength=strength,
        worst_corner=worst_corner or None,
        worst_corner_loss_s=float(worst_loss),
        confidence=conf,
        track_state=state,
        headline="",
        evidence=evidence,
    )
    diag.headline = _headline(diag)
    return diag
