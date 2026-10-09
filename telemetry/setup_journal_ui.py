"""Streamlit panels for the setup journal: follow-up card, runs, A/B compare, experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from .db import get_session
from .runs import runs_frame
from .session_compare import session_label
from .setup_eval import (
    compare_sessions_runs,
    load_session_runs,
    previous_comparable,
    sessions_on_track,
)
from .setup_log import followup_entries, get_recommendations, list_experiments
from .setup_tweaker import SETUP_PARAMS

_LABELS = {p.key: p.label for p in SETUP_PARAMS}
_VERDICT_ICON = {"better": "✅", "worse": "⚠️", "neutral": "➖", "inconclusive": "❔"}
_STATUS_TEXT = {
    "applied": "applied",
    "partial": "partly applied",
    "ignored": "not applied",
    "pending": "waiting for the next session",
}


def _label(key: str) -> str:
    return _LABELS.get(key, key)


def _fmt_s(x: float | None) -> str:
    return f"{x:+.3f}s" if x is not None and pd.notna(x) else "—"


def _fmt_value(key: str, v: Any) -> str:
    if v is None:
        return "—"
    p = next((p for p in SETUP_PARAMS if p.key == key), None)
    if p is None:
        return f"{v:.3g}"
    shown = float(v) * p.display_scale
    return f"{shown:.2f}".rstrip("0").rstrip(".")


def setup_diff_frame(diff: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for d in diff:
        key = d["key"]
        delta = d.get("delta")
        p = next((p for p in SETUP_PARAMS if p.key == key), None)
        rows.append(
            {
                "Parameter": _label(key),
                "From": _fmt_value(key, d.get("from")),
                "To": _fmt_value(key, d.get("to")),
                "Δ": (f"{delta * p.display_scale:+.3g}" if delta is not None and p is not None else "—"),
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- follow-up card


def render_followup_cards(session: dict[str, Any], app_root: Path) -> None:
    """Did earlier advice get used, and did it help? Plus what is still waiting for a follow-up."""
    sid = int(session["id"])
    entries = followup_entries(sid, app_root)

    for entry in entries:
        rec, app, exp, symptom = entry["rec"], entry["application"], entry["experiment"], entry["symptom"]
        n_total = len(rec["changes"])
        icon = _VERDICT_ICON.get((exp or {}).get("verdict"), "❔")
        head = (
            f"{icon} Suggestion from session #{rec['session_id']} ({symptom}, {rec['variant']}): "
            f"{len(app.applied)}/{n_total} applied"
        )
        if exp and exp.get("pace_delta") is not None:
            head += f" → {_fmt_s(exp['pace_delta'])} ±{exp['noise']:.2f}s (fuel-corrected) · {exp['verdict']}"
        elif exp is None:
            head += " → no measurable garage change to score"
        with st.container(border=True):
            st.markdown(f"**{head}**")
            bits = []
            if app.applied:
                bits.append("applied: " + ", ".join(_label(k) for k in app.applied))
            if app.missed:
                bits.append("not applied: " + ", ".join(_label(k) for k in app.missed))
            if app.opposite:
                bits.append("moved the other way: " + ", ".join(_label(k) for k in app.opposite))
            if bits:
                st.caption(" · ".join(bits))
            if exp:
                sym = exp.get("symptom") or {}
                if sym.get("delta") is not None:
                    state = "shrank" if sym.get("fixed") else ("grew" if sym.get("worse") else "barely moved")
                    st.caption(f"The {symptom} symptom {state} ({sym['delta']:+.2f} on the diagnosed phase).")
                if exp["source"] == "mixed":
                    st.caption("You also changed other things by hand, so the result is shared between them.")

    pending_here = [r for r in get_recommendations(app_root, session_id=sid) if r["status"] == "pending"]
    if pending_here and not entries:
        names = ", ".join(sorted({r["variant"] for r in pending_here}))
        st.caption(
            f"Advice saved for this session ({names}). Import your next session on this track and it will be scored here."
        )


# --------------------------------------------------------------------------- runs + compare


def render_runs_panel(session: dict[str, Any], app_root: Path) -> None:
    runs = load_session_runs(int(session["id"]), app_root)
    if not runs:
        st.caption("No runs found in this session.")
        return
    st.dataframe(runs_frame(runs), use_container_width=True, hide_index=True)
    st.caption(
        "A run is a stretch of laps on the same garage and tyre set. Pace is corrected to 5 kg of fuel "
        "(0.03 s/kg); *quali* runs are judged on their best lap, *race* runs on their pace over the fastest 60% of laps."
    )


def render_compare_panel(session: dict[str, Any], track: str, app_root: Path, key: str) -> None:
    sid = int(session["id"])
    mode_label = st.radio("Compare", ["Quali", "Race"], horizontal=True, key=f"{key}_mode")
    mode = mode_label.lower()

    sessions = sessions_on_track(track, app_root)
    earlier = sessions[sessions["id"].astype(int) != sid]
    if sessions.empty or earlier.empty:
        st.caption("No other session on this track yet.")
        return
    ids = sessions["id"].astype(int).tolist()
    earlier = earlier[earlier["id"].astype(int).map(lambda i: ids.index(i) < ids.index(sid))]
    if earlier.empty:
        st.caption("This is the first session on this track — nothing earlier to compare with.")
        return
    options = earlier.sort_values(["created_at", "id"], ascending=False)["id"].astype(int).tolist()
    default = previous_comparable(track, sid, mode, app_root)
    index = options.index(int(default["id"])) if default and int(default["id"]) in options else 0
    ref_id = st.selectbox(
        "Reference session",
        options,
        index=index,
        format_func=lambda i: session_label(get_session(i, app_root) or {"id": i}),
        key=f"{key}_ref_{mode}",
    )

    comp = compare_sessions_runs(int(ref_id), sid, mode, app_root)
    if comp is None:
        st.info(f"One of the two sessions has no {mode} run to compare.")
        return

    msg = f"{_VERDICT_ICON[comp.verdict]} **{comp.verdict.capitalize()}** — {comp.verdict_reason}"
    {"better": st.success, "worse": st.warning, "neutral": st.info, "inconclusive": st.info}[comp.verdict](msg)
    for w in comp.warnings:
        st.caption(f"⚠ {w}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pace Δ (fuel-corr.)", _fmt_s(comp.pace_delta), help="Negative = this session is faster.")
    c2.metric("Noise band", f"±{comp.noise:.2f}s")
    c3.metric("Degradation Δ", f"{comp.deg_delta:+.3f}s/lap" if comp.deg_delta is not None else "—")
    c4.metric("Tyre wear Δ", f"{comp.wear_delta:+.2f}%/lap" if comp.wear_delta is not None else "—")

    st.markdown("**Garage changes**")
    if comp.setup_diff:
        st.dataframe(setup_diff_frame(comp.setup_diff), use_container_width=True, hide_index=True)
    else:
        st.caption("Identical mechanical setup — any pace difference here is driver / track / conditions, not the car.")

    if comp.balance_delta:
        st.markdown("**Balance score change** (+ = more understeer, − = more oversteer)")
        cols = st.columns(3)
        for col, phase in zip(cols, ("entry", "mid", "exit")):
            if phase in comp.balance_delta:
                was = comp.run_a.balance.get(f"{phase}_score", 0.0)
                now = comp.run_b.balance.get(f"{phase}_score", 0.0)
                col.metric(phase.capitalize(), f"{now:+.2f}", f"{now - was:+.2f}", delta_color="off")
    extras = []
    if comp.temp_delta.get("temp_front") is not None:
        extras.append(f"front temps {comp.temp_delta['temp_front']:+.1f}°C")
    if comp.temp_delta.get("temp_rear") is not None:
        extras.append(f"rear temps {comp.temp_delta['temp_rear']:+.1f}°C")
    if comp.lockup_delta is not None:
        extras.append(f"lock-up share {comp.lockup_delta * 100:+.1f}pp")
    if extras:
        st.caption(" · ".join(extras))
    if comp.corner_deltas:
        st.markdown("**Corners that moved most** (negative = faster in this session)")
        st.dataframe(
            pd.DataFrame(
                [{"Corner": c["corner"], "Δ time": f"{c['delta_s']:+.3f}s"} for c in comp.corner_deltas]
            ),
            use_container_width=True,
            hide_index=True,
        )


def experiments_frame(track: str, app_root: Path) -> pd.DataFrame:
    rows = []
    for e in list_experiments(track, app_root):
        changes = ", ".join(
            f"{_label(c['key'])} {c['delta'] * (next((p.display_scale for p in SETUP_PARAMS if p.key == c['key']), 1.0)):+.3g}"
            for c in e["changes"][:4]
            if c.get("delta") is not None
        )
        if len(e["changes"]) > 4:
            changes += f" (+{len(e['changes']) - 4} more)"
        rows.append(
            {
                "From → to": f"#{e['from_session_id']} → #{e['to_session_id']}",
                "Mode": e["mode"],
                "Changes": changes,
                "Pace (fuel-corr.)": _fmt_s(e["pace_delta"]),
                "Noise": f"±{e['noise']:.2f}s" if e.get("noise") else "—",
                "Verdict": f"{_VERDICT_ICON.get(e['verdict'], '')} {e['verdict']}",
                "Source": e["source"],
            }
        )
    return pd.DataFrame(rows)
