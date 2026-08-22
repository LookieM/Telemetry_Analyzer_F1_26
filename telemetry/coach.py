"""Unified coach feed: collect, dedupe, rank engineer callouts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .conditions import STATE_LABELS, weather_banner
from .corner_engineer import corner_engineer_callouts
from .diagnosis import LapDiagnosis
from .ers import channels_2026_insights, practice_ers_insights
from .insights import Insight, generate_insights
from .race_windows import stint_window_insights
from .stint_coach import StintTip, stint_saving_insights


@dataclass
class CoachItem:
    id: str
    source: str  # corner | insights | ers | stint | setup | windows | diagnosis
    domain: str  # technique | energy | tyres | fuel | setup | weather
    action_kind: str  # drive | setup | manage | observe
    severity: str  # info | tip | warning
    priority: float
    confidence: float
    title: str
    detail: str
    related_keys: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.priority * self.confidence


def _sev_boost(severity: str) -> float:
    return {"warning": 1.25, "tip": 1.0, "info": 0.55}.get(severity, 0.7)


def _item(
    *,
    id: str,
    source: str,
    domain: str,
    action_kind: str,
    severity: str,
    priority: float,
    confidence: float,
    title: str,
    detail: str,
    related_keys: list[str] | None = None,
) -> CoachItem:
    return CoachItem(
        id=id,
        source=source,
        domain=domain,
        action_kind=action_kind,
        severity=severity,
        priority=float(priority) * _sev_boost(severity),
        confidence=float(confidence),
        title=title,
        detail=detail,
        related_keys=list(related_keys or []),
    )


def _insight_to_item(ins: Insight, confidence: float) -> CoachItem:
    domain_map = {
        "inputs": "technique",
        "braking": "technique",
        "tyres": "tyres",
        "weather": "weather",
        "data": "technique",
        "energy": "energy",
        "fuel": "fuel",
    }
    domain = domain_map.get(ins.category, "technique")
    action = "drive" if domain in ("technique", "tyres") else "observe"
    if ins.category == "weather":
        action = "observe"
    related = []
    title_l = ins.title.lower()
    if "coast" in title_l or "lift" in ins.detail.lower():
        related = ["coast"]
    elif "lock" in title_l:
        related = ["lockup"]
    elif "tyre" in title_l or ins.category == "tyres":
        related = ["tyre_temps"]
    elif "brake" in title_l:
        related = ["braking"]
    elif "partial throttle" in title_l:
        related = ["throttle"]
    pri = 35.0 if ins.severity == "warning" else (22.0 if ins.severity == "tip" else 8.0)
    return _item(
        id=f"insights:{ins.title}",
        source="insights",
        domain=domain,
        action_kind=action,
        severity=ins.severity,
        priority=pri,
        confidence=confidence,
        title=ins.title,
        detail=ins.detail,
        related_keys=related,
    )


def _stint_to_item(tip: StintTip, confidence: float) -> CoachItem:
    domain = {"tyre": "tyres", "fuel": "fuel", "technique": "technique", "weather": "weather"}.get(
        tip.category, "fuel"
    )
    action = "manage" if domain in ("fuel", "tyres") else "drive"
    related = []
    tl = tip.title.lower()
    if "coast" in tl or "lift" in tip.detail.lower():
        related = ["coast"]
    elif "lock" in tl:
        related = ["lockup"]
    elif "tyre" in tl or tip.category == "tyre":
        related = ["tyre_temps"]
    pri = 30.0 if tip.severity == "warning" else (18.0 if tip.severity == "tip" else 6.0)
    return _item(
        id=f"stint:{tip.title}",
        source="stint",
        domain=domain,
        action_kind=action,
        severity=tip.severity,
        priority=pri,
        confidence=confidence,
        title=tip.title,
        detail=tip.detail,
        related_keys=related,
    )


def _ers_to_item(tip, confidence: float) -> CoachItem:
    pri = 28.0 if tip.severity == "warning" else 16.0
    return _item(
        id=f"ers:{tip.title}",
        source="ers",
        domain="energy",
        action_kind="manage",
        severity=tip.severity,
        priority=pri,
        confidence=confidence * 0.9,
        title=tip.title,
        detail=tip.detail,
        related_keys=["ers"],
    )


def _corner_to_item(callout, confidence: float) -> CoachItem:
    pri = 40.0 + min(60.0, callout.delta_s * 120.0)
    return _item(
        id=f"corner:{callout.corner_id}",
        source="corner",
        domain="technique",
        action_kind="drive",
        severity=callout.severity,
        priority=pri,
        confidence=confidence,
        title=callout.corner_name or callout.corner_id,
        detail=callout.sentence,
        related_keys=[f"corner:{callout.corner_id}", "braking"],
    )


def _diagnosis_items(diag: LapDiagnosis) -> list[CoachItem]:
    items: list[CoachItem] = []
    banner = diag.evidence.get("weather_banner")
    if banner:
        items.append(
            _item(
                id="diagnosis:weather",
                source="diagnosis",
                domain="weather",
                action_kind="observe",
                severity="info",
                priority=12.0,
                confidence=diag.confidence,
                title=f"Track state: {STATE_LABELS.get(diag.track_state, diag.track_state)}",
                detail=banner,
                related_keys=["weather"],
            )
        )
    if diag.worst_corner_loss_s >= 0.03 and diag.worst_corner:
        rc = diag.evidence.get("recurring_corners") or []
        lap_n = rc[0][2] if rc and rc[0][0] == diag.worst_corner else None
        if lap_n is not None and diag.evidence.get("scope") == "session":
            detail = (
                f"Avg +{diag.worst_corner_loss_s:.3f}s vs PB on {lap_n} laps — "
                "this is your highest-impact sector to fix session-wide."
            )
        else:
            detail = f"Largest time loss vs reference (+{diag.worst_corner_loss_s:.3f}s). Fix here first."
        items.append(
            _item(
                id="diagnosis:worst_corner",
                source="diagnosis",
                domain="technique",
                action_kind="drive",
                severity="tip" if diag.worst_corner_loss_s < 0.12 else "warning",
                priority=35.0 + diag.worst_corner_loss_s * 100.0,
                confidence=diag.confidence,
                title=f"Priority corner: {diag.worst_corner}",
                detail=detail,
                related_keys=[f"corner:{diag.worst_corner}", "technique"],
            )
        )
    if diag.primary_issue != "balanced" and diag.strength != "none":
        drive_first = (
            "Try driving fixes (markers, throttle) on the next push before changing the garage."
        )
        votes = diag.evidence.get("issue_votes") or {}
        vote_n = sum(int(v) for v in votes.values())
        if diag.evidence.get("scope") == "session" and vote_n >= 2:
            balance_detail = (
                f"{diag.strength.capitalize()} {diag.primary_issue} in {diag.phase} "
                f"showed up on {vote_n} laps this session. {drive_first}"
            )
        else:
            balance_detail = (
                f"{diag.strength.capitalize()} {diag.primary_issue} in {diag.phase}. {drive_first}"
            )
        items.append(
            _item(
                id="diagnosis:balance",
                source="diagnosis",
                domain="setup" if diag.strength == "strong" else "technique",
                action_kind="drive" if diag.strength != "strong" else "setup",
                severity="tip",
                priority=32.0,
                confidence=diag.confidence,
                title=f"Balance: {diag.primary_issue} ({diag.phase})",
                detail=balance_detail,
                related_keys=["balance", diag.primary_issue],
            )
        )
    return items


def _session_recurring_corner_items(diag: LapDiagnosis) -> list[CoachItem]:
    items: list[CoachItem] = []
    rc = diag.evidence.get("recurring_corners") or []
    conf = diag.confidence
    for name, avg_loss, lap_n in rc[:3]:
        if avg_loss < 0.025:
            continue
        # Skip duplicate of priority corner item
        if name == diag.worst_corner and len(rc) == 1:
            continue
        items.append(
            _item(
                id=f"session:corner:{name}",
                source="corner",
                domain="technique",
                action_kind="drive",
                severity="tip" if avg_loss < 0.08 else "warning",
                priority=30.0 + avg_loss * 80.0 + lap_n * 2.0,
                confidence=conf,
                title=f"Recurring loss: {name}",
                detail=f"Avg +{avg_loss:.3f}s vs your PB on {lap_n} laps — not a one-off mistake.",
                related_keys=[f"corner:{name}", "technique"],
            )
        )
    return items


def _session_pattern_items(df: pd.DataFrame, sample_laps: list[int], conf: float) -> list[CoachItem]:
    from .metrics import get_lap

    items: list[CoachItem] = []
    if not sample_laps:
        return items

    high_coast = 0
    high_lock = 0
    partial_thr = 0
    for lap_n in sample_laps:
        lap_df = get_lap(df, lap_n)
        if lap_df.empty:
            continue
        if "coasting" in lap_df.columns and "speed" in lap_df.columns:
            if float((lap_df["coasting"] & (lap_df["speed"] > 120)).mean()) > 0.04:
                high_coast += 1
        if "lockup_risk" in lap_df.columns and int(lap_df["lockup_risk"].sum()) > 15:
            high_lock += 1
        if "throttle" in lap_df.columns and "brake" in lap_df.columns:
            partial = (lap_df["throttle"] > 0.15) & (lap_df["throttle"] < 0.85) & (lap_df["brake"] < 0.05)
            if float(partial.mean()) > 0.12:
                partial_thr += 1

    n = len(sample_laps)
    if high_coast >= max(2, n // 3):
        items.append(
            _item(
                id="session:coast",
                source="insights",
                domain="technique",
                action_kind="drive",
                severity="tip",
                priority=24.0,
                confidence=conf,
                title="Coasting while fast (session)",
                detail=f"High-speed coasting on {high_coast}/{n} laps — commit to brake or throttle earlier.",
                related_keys=["coast"],
            )
        )
    if high_lock >= max(2, n // 3):
        items.append(
            _item(
                id="session:lockup",
                source="insights",
                domain="technique",
                action_kind="drive",
                severity="warning",
                priority=32.0,
                confidence=conf,
                title="Lockups keep appearing",
                detail=f"Significant lockups on {high_lock}/{n} laps — adjust markers or bias session-wide.",
                related_keys=["lockup"],
            )
        )
    if partial_thr >= max(2, n // 3):
        items.append(
            _item(
                id="session:partial_throttle",
                source="insights",
                domain="technique",
                action_kind="drive",
                severity="tip",
                priority=20.0,
                confidence=conf * 0.9,
                title="Hesitation on exit (session)",
                detail=f"Mid-throttle on {partial_thr}/{n} laps — often a session-wide exit technique issue.",
                related_keys=["throttle"],
            )
        )
    return items


def collect_session_coach_items(
    df: pd.DataFrame,
    *,
    diagnosis: LapDiagnosis,
    best_lap: int,
    track: str | None = None,
    track_length: float | None = None,
    conditions: str | None = None,
    include_setup_summary: tuple[list[Any], list[str]] | None = None,
) -> list[CoachItem]:
    """Gather session-wide coach items — trends and recurring issues vs PB."""
    from .ers import channels_2026_insights, session_ers_insights
    from .insights import generate_insights
    from .stint_coach import session_stint_insights

    conf = diagnosis.confidence
    items: list[CoachItem] = []
    items.extend(_diagnosis_items(diagnosis))
    items.extend(_session_recurring_corner_items(diagnosis))

    sample_laps = list(diagnosis.evidence.get("sample_laps") or [])
    items.extend(_session_pattern_items(df, sample_laps, conf))

    # PB lap technique baseline (not per selected lap)
    for ins in generate_insights(
        df,
        best_lap,
        reference_lap=best_lap,
        track=track,
        track_length=track_length,
        conditions=conditions,
    ):
        if ins.severity == "info":
            continue
        if ins.category == "weather" and any(i.related_keys == ["weather"] for i in items):
            continue
        items.append(_insight_to_item(ins, conf * 0.85))

    for tip in session_stint_insights(df, best_lap=best_lap, conditions=conditions):
        if tip.severity == "info":
            continue
        items.append(_stint_to_item(tip, conf))

    for tip in session_ers_insights(df, track=track, track_length=track_length):
        if tip.severity in ("tip", "warning"):
            items.append(_ers_to_item(tip, conf))

    for tip in channels_2026_insights(df, best_lap, reference_lap=best_lap):
        if tip.severity in ("tip", "warning"):
            items.append(_ers_to_item(tip, conf * 0.85))

    for tip in stint_window_insights(df, track_length_m=track_length):
        if tip.severity in ("tip", "warning"):
            items.append(_stint_to_item(tip, conf * 0.9))

    if include_setup_summary:
        changes, findings = include_setup_summary
        items.append(setup_summary_item(diagnosis, changes, findings))

    return items


def setup_summary_item(diag: LapDiagnosis, changes: list[Any], findings: list[str]) -> CoachItem:
    mech = [c for c in changes if getattr(c, "key", None) != "fuel_setup"]
    if mech:
        lines = [f"{c.label}: {c.before:.2g} → {c.after:.2g}" for c in mech[:4]]
        detail = "; ".join(lines)
        if len(mech) > 4:
            detail += f" (+{len(mech) - 4} more)"
    else:
        detail = findings[-1] if findings else "No mechanical changes suggested."
    return _item(
        id="setup:summary",
        source="setup",
        domain="setup",
        action_kind="setup",
        severity="info",
        priority=25.0,
        confidence=diag.confidence * 0.85,
        title=f"Garage direction: {diag.primary_issue} ({diag.phase})",
        detail=detail,
        related_keys=["setup", "balance"],
    )


def collect_coach_items(
    df: pd.DataFrame,
    focus_lap: int,
    *,
    ref_lap: int | None = None,
    diagnosis: LapDiagnosis | None = None,
    corner_cmp: pd.DataFrame | None = None,
    track: str | None = None,
    track_length: float | None = None,
    conditions: str | None = None,
    use_stored_insights: list[dict] | None = None,
    include_setup_summary: tuple[list[Any], list[str]] | None = None,
) -> list[CoachItem]:
    """Gather tips from all producers into one list."""
    if diagnosis is None:
        from .diagnosis import build_lap_diagnosis

        diagnosis = build_lap_diagnosis(
            df,
            focus_lap,
            ref_lap=ref_lap,
            corner_cmp=corner_cmp,
            conditions=conditions,
            track=track,
            track_length=track_length,
        )

    conf = diagnosis.confidence
    items: list[CoachItem] = []
    items.extend(_diagnosis_items(diagnosis))

    # Corners
    if corner_cmp is not None and not corner_cmp.empty:
        for c in corner_engineer_callouts(corner_cmp, top_n=4):
            items.append(_corner_to_item(c, conf))

    # Insights — live preferred unless stored explicitly passed and ref matches
    if use_stored_insights:
        for raw in use_stored_insights:
            ins = Insight(
                severity=raw.get("severity", "info"),
                title=raw.get("title", ""),
                detail=raw.get("detail", ""),
                category=raw.get("category", "inputs"),
            )
            items.append(_insight_to_item(ins, conf * 0.85))
    else:
        for ins in generate_insights(
            df,
            focus_lap,
            reference_lap=ref_lap,
            track=track,
            track_length=track_length,
            conditions=conditions,
        ):
            # Skip duplicate weather if diagnosis already has it
            if ins.category == "weather" and any(i.related_keys == ["weather"] for i in items):
                continue
            items.append(_insight_to_item(ins, conf))

    # Stint / fuel
    for tip in stint_saving_insights(df, focus_lap, reference_lap=ref_lap, conditions=conditions):
        if tip.severity == "info" and tip.title in ("Fuel this lap", "Tyre temperatures", "Tyre wear this lap"):
            continue  # drop low-signal info duplicates
        items.append(_stint_to_item(tip, conf))

    # ERS — tips/warnings only
    for tip in practice_ers_insights(
        df, focus_lap, reference_lap=ref_lap, track=track, track_length=track_length
    ):
        if tip.severity in ("tip", "warning"):
            items.append(_ers_to_item(tip, conf))
    for tip in channels_2026_insights(df, focus_lap, reference_lap=ref_lap):
        if tip.severity in ("tip", "warning"):
            items.append(_ers_to_item(tip, conf * 0.85))

    # Race windows — warnings/tips only
    for tip in stint_window_insights(df, track_length_m=track_length):
        if tip.severity in ("tip", "warning"):
            items.append(_stint_to_item(tip, conf * 0.9))

    if include_setup_summary:
        changes, findings = include_setup_summary
        items.append(setup_summary_item(diagnosis, changes, findings))

    return items


def _coast_conflict(items: list[CoachItem]) -> list[CoachItem]:
    """Resolve coast: fuel-saving vs pace — prefer fuel-critical add-lift-coast."""
    coast = [i for i in items if "coast" in i.related_keys]
    if len(coast) <= 1:
        return items
    add_lift = [i for i in coast if "lift" in i.detail.lower() or "little lift" in i.title.lower()]
    shorten = [i for i in coast if "shorten" in i.detail.lower() or "coasting while fast" in i.title.lower()]
    if add_lift and shorten:
        drop_ids = {i.id for i in shorten}
        # Keep higher-scored coast advice
        best = max(coast, key=lambda x: x.score)
        drop_ids = {i.id for i in coast if i.id != best.id}
        return [i for i in items if i.id not in drop_ids]
    return items


def _lockup_conflict(items: list[CoachItem]) -> list[CoachItem]:
    lock = [i for i in items if "lockup" in i.related_keys]
    if len(lock) <= 1:
        return items
    best = max(lock, key=lambda x: x.score)
    drop = {i.id for i in lock if i.id != best.id}
    return [i for i in items if i.id not in drop]


def _tyre_conflict(items: list[CoachItem]) -> list[CoachItem]:
    tyre = [i for i in items if "tyre_temps" in i.related_keys]
    if len(tyre) <= 1:
        return items
    best = max(tyre, key=lambda x: x.score)
    drop = {i.id for i in tyre if i.id != best.id}
    return [i for i in items if i.id not in drop]


def dedupe_and_resolve(items: list[CoachItem]) -> list[CoachItem]:
    """Merge duplicates and resolve known conflicts."""
    if not items:
        return []

    # Exact id dedupe — keep highest score
    by_id: dict[str, CoachItem] = {}
    for it in items:
        prev = by_id.get(it.id)
        if prev is None or it.score > prev.score:
            by_id[it.id] = it
    items = list(by_id.values())

    # related_keys overlap — keep best per key group (except corner:* which are unique)
    grouped: dict[str, CoachItem] = {}
    passthrough: list[CoachItem] = []
    for it in items:
        keys = [k for k in it.related_keys if not k.startswith("corner:")]
        if not keys:
            passthrough.append(it)
            continue
        main = keys[0]
        prev = grouped.get(main)
        if prev is None or it.score > prev.score:
            grouped[main] = it
    items = passthrough + list(grouped.values())

    items = _coast_conflict(items)
    items = _lockup_conflict(items)
    items = _tyre_conflict(items)

    # Prefer drive before setup when scores are close
    drive = [i for i in items if i.action_kind == "drive"]
    setup = [i for i in items if i.action_kind == "setup"]
    if drive and setup:
        best_drive = max(drive, key=lambda x: x.score)
        items = [
            i
            for i in items
            if i.action_kind != "setup" or i.score >= best_drive.score * 0.85 or i.source == "setup"
        ]

    return items


def rank_coach_items(items: list[CoachItem], limit: int = 8) -> tuple[list[CoachItem], list[CoachItem]]:
    """Return (top ranked, remainder sorted by score)."""
    resolved = dedupe_and_resolve(items)
    resolved.sort(key=lambda x: x.score, reverse=True)
    top = resolved[:limit]
    rest = resolved[limit:]
    return top, rest


def coach_feed_for_session(
    df: pd.DataFrame,
    focus_lap: int | None = None,
    *,
    ref_lap: int | None = None,
    corner_cmp: pd.DataFrame | None = None,
    track: str | None = None,
    track_length: float | None = None,
    conditions: str | None = None,
    stored_insights: list[dict] | None = None,
    prefer_live: bool = True,
    extra_items: list[CoachItem] | None = None,
    best_lap: int | None = None,
) -> tuple[LapDiagnosis, list[CoachItem], list[CoachItem]]:
    """Build session diagnosis + ranked coach feed (whole stint, not one lap)."""
    from .diagnosis import build_session_diagnosis
    from .metrics import build_lap_summary

    summary = build_lap_summary(df, track_length=track_length)
    if best_lap is None and not summary.empty:
        best_lap = int(summary.loc[summary["is_best"], "lap"].iloc[0])
    elif best_lap is None:
        best_lap = int(focus_lap or 1)

    diag = build_session_diagnosis(
        df,
        best_lap=best_lap,
        conditions=conditions,
        track=track,
        track_length=track_length,
    )
    raw = collect_session_coach_items(
        df,
        diagnosis=diag,
        best_lap=best_lap,
        track=track,
        track_length=track_length,
        conditions=conditions,
    )
    if extra_items:
        raw.extend(extra_items)
    top, rest = rank_coach_items(raw, limit=8)
    return diag, top, rest
