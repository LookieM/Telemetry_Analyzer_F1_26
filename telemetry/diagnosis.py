"""Shared lap diagnosis for coach + setup engineer."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .conditions import STATE_LABELS, _as_state, weather_banner
from .corner_engineer import corner_engineer_callouts
from .metrics import build_lap_summary, get_lap, is_probable_lap


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


def _probable_lap_numbers(
    df: pd.DataFrame,
    summary: pd.DataFrame,
    *,
    track_length: float | None,
) -> list[int]:
    laps: list[int] = []
    for _, row in summary.iterrows():
        lap_n = int(row["lap"])
        lap_df = get_lap(df, lap_n)
        lap_time = row.get("lap_time")
        if is_probable_lap(lap_df, float(lap_time) if pd.notna(lap_time) else None, track_length=track_length):
            laps.append(lap_n)
    return laps


def _session_recurring_corners(
    df: pd.DataFrame,
    *,
    track: str | None,
    track_length: float | None,
    best_lap: int,
    sample_laps: list[int],
    min_laps: int = 2,
    min_loss_s: float = 0.025,
) -> list[tuple[str, float, int]]:
    """Corners that consistently lose time vs session PB — (name, avg loss, lap count)."""
    from .corners import analyze_lap_corners, compare_corners

    ref_corners = analyze_lap_corners(get_lap(df, best_lap), track, track_length=track_length)
    if ref_corners.empty:
        return []

    by_id: dict[str, list[float]] = {}
    names: dict[str, str] = {}
    for lap_n in sample_laps:
        if lap_n == best_lap:
            continue
        focus_corners = analyze_lap_corners(get_lap(df, lap_n), track, track_length=track_length)
        if focus_corners.empty:
            continue
        cmp = compare_corners(focus_corners, ref_corners)
        if cmp.empty or "delta_s" not in cmp.columns:
            continue
        for _, row in cmp.iterrows():
            delta = row.get("delta_s")
            if pd.isna(delta) or float(delta) < min_loss_s:
                continue
            cid = str(row.get("corner_id") or "")
            if not cid:
                continue
            by_id.setdefault(cid, []).append(float(delta))
            names[cid] = str(row.get("corner_name") or cid)

    ranked: list[tuple[str, float, int]] = []
    for cid, losses in by_id.items():
        if len(losses) < min_laps:
            continue
        ranked.append((names.get(cid, cid), float(sum(losses) / len(losses)), len(losses)))
    ranked.sort(key=lambda x: (x[1] * x[2], x[1]), reverse=True)
    return ranked[:5]


def _session_headline(d: LapDiagnosis, ev: dict[str, Any]) -> str:
    parts: list[str] = []
    n = int(ev.get("session_lap_count") or 0)
    best = ev.get("best_lap")
    best_t = ev.get("best_time")
    if n and best is not None and best_t is not None:
        parts.append(f"Session · {n} laps · PB L{best} ({float(best_t):.3f}s)")
    else:
        parts.append("Session overview")

    spread = float(ev.get("pace_spread_s") or 0.0)
    if spread >= 0.8 and n >= 3:
        parts.append(f"pace spread {spread:.2f}s")

    trend = ev.get("pace_trend") or "stable"
    if trend == "falling_off":
        parts.append("pace tailing off late stint")
    elif trend == "improving":
        parts.append("pace improving through session")

    rc = ev.get("recurring_corners") or []
    if rc:
        labels = ", ".join(r[0] for r in rc[:2])
        parts.append(f"recurring loss {labels}")

    votes = ev.get("issue_votes") or {}
    vote_n = sum(int(v) for v in votes.values())
    if d.primary_issue != "balanced" and vote_n >= 2:
        parts.append(f"{d.primary_issue} ({d.phase}) on {vote_n} laps")
    elif d.primary_issue != "balanced":
        parts.append(f"{d.primary_issue} ({d.phase}, {d.strength})")
    elif not rc and trend == "stable":
        parts.append("repeat PB pace — refine consistency")

    wx = STATE_LABELS.get(d.track_state, "")
    if wx and d.track_state != "dry":
        parts.append(wx.lower())
    return " · ".join(parts)


def build_session_diagnosis(
    df: pd.DataFrame,
    *,
    best_lap: int | None = None,
    conditions: str | None = None,
    track: str | None = None,
    track_length: float | None = None,
) -> LapDiagnosis:
    """Session-wide diagnosis: trends and recurring issues vs the PB lap."""
    from .setup_builder import analyze_practice_balance

    state = _as_state(conditions)
    summary = build_lap_summary(df, track_length=track_length)
    if summary.empty:
        return build_lap_diagnosis(
            df,
            int(best_lap or 1),
            ref_lap=best_lap,
            conditions=conditions,
            track=track,
            track_length=track_length,
        )

    if best_lap is None or best_lap not in summary["lap"].values:
        best_lap = int(summary.loc[summary["is_best"], "lap"].iloc[0])

    sample_laps = _probable_lap_numbers(df, summary, track_length=track_length)
    if best_lap not in sample_laps:
        sample_laps.append(best_lap)

    issue_counts: Counter[str] = Counter()
    phase_counts: Counter[str] = Counter()
    strength_rank = {"none": 0, "mild": 1, "medium": 2, "strong": 3}
    strength_max = "none"
    for lap_n in sample_laps:
        bal = analyze_practice_balance(df, lap=lap_n) or {}
        issue = str(bal.get("issue") or "balanced")
        if issue == "balanced":
            continue
        issue_counts[issue] += 1
        phase_counts[str(bal.get("issue_phase") or "all")] += 1
        s = str(bal.get("issue_strength") or "mild")
        if strength_rank.get(s, 0) > strength_rank.get(strength_max, 0):
            strength_max = s

    if issue_counts:
        primary_issue = issue_counts.most_common(1)[0][0]
        phase = phase_counts.most_common(1)[0][0]
        vote_n = issue_counts[primary_issue]
        strength = strength_max if vote_n >= max(2, len(sample_laps) // 4) else "mild"
    else:
        primary_issue, phase, strength = "balanced", "all", "none"

    recurring = _session_recurring_corners(
        df,
        track=track,
        track_length=track_length,
        best_lap=best_lap,
        sample_laps=sample_laps,
    )
    worst_corner = recurring[0][0] if recurring else None
    worst_loss = recurring[0][1] if recurring else 0.0

    ordered = summary.sort_values("lap")
    pace_trend = "stable"
    if len(ordered) >= 6:
        third = max(1, len(ordered) // 3)
        early = float(ordered.head(third)["lap_time"].mean())
        late = float(ordered.tail(third)["lap_time"].mean())
        if late - early > 0.25:
            pace_trend = "falling_off"
        elif early - late > 0.25:
            pace_trend = "improving"

    best_time = float(summary.loc[summary["lap"] == best_lap, "lap_time"].iloc[0])
    spread = float(summary["lap_time"].max() - summary["lap_time"].min())
    balance = analyze_practice_balance(df, lap=best_lap) or {}

    conf = 0.50
    if len(sample_laps) >= 4:
        conf += 0.15
    if len(sample_laps) >= 10:
        conf += 0.10
    if recurring:
        conf += 0.10
    if issue_counts:
        conf += 0.05
    if balance.get("temp_avg") is not None:
        conf += 0.05
    conf = float(min(1.0, conf))

    evidence: dict[str, Any] = {
        "scope": "session",
        "balance": balance,
        "session_lap_count": len(sample_laps),
        "best_lap": best_lap,
        "best_time": best_time,
        "pace_spread_s": spread,
        "pace_trend": pace_trend,
        "recurring_corners": recurring,
        "issue_votes": dict(issue_counts),
        "sample_laps": sample_laps,
        "lockup_frac": balance.get("lockup_frac"),
        "coast_pct": balance.get("coast_pct"),
        "wot_pct": balance.get("wot_pct"),
        "temp_spread_axle": balance.get("temp_spread_axle"),
        "temp_avg": balance.get("temp_avg"),
        "weather_banner": weather_banner(state),
    }

    diag = LapDiagnosis(
        focus_lap=int(best_lap),
        ref_lap=int(best_lap),
        lap_time=best_time,
        ref_time=best_time,
        time_loss_s=0.0,
        primary_issue=primary_issue,
        phase=phase,
        strength=strength,
        worst_corner=worst_corner,
        worst_corner_loss_s=float(worst_loss),
        confidence=conf,
        track_state=state,
        headline="",
        evidence=evidence,
    )
    diag.headline = _session_headline(diag, evidence)
    return diag
