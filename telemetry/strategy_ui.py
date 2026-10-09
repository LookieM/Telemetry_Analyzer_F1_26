"""Streamlit Strategy tab / planner: model inputs, ranked plans, pit windows, race trace, calls, review."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from .compounds import Allocation, c_label, get_allocation, softness
from .corners import normalize_track_name
from .strategy import (
    CompoundSpec,
    Plan,
    RaceParams,
    actual_plan,
    apply_overrides,
    clear_overrides,
    default_params,
    game_pit_windows,
    lap_times,
    load_overrides,
    optimise,
    race_calls,
    review_race,
    save_overrides,
    sensitivity,
    specs_from_model,
)
from .tyres import TrackTyreModel, track_compound_model
from .tyres_ui import wear_limit
from .ui.uplot import pane, series, stint_timeline, trace_chart

TOP_PLANS = 8
CHART_PLANS = 4
# Placeholder model for a track with no long runs yet (one softness step apart; edit before use).
_MANUAL = {"S": (-0.5, 0.25, 6.0), "M": (0.0, 0.15, 4.5), "H": (0.45, 0.09, 3.0)}


def _manual_specs(alloc: Allocation) -> list[CompoundSpec]:
    out = []
    for code, role in sorted(alloc.roles.items(), key=lambda kv: -softness(kv[0])):
        if role not in _MANUAL:
            continue
        off, deg, wear = _MANUAL[role]
        out.append(CompoundSpec(code, alloc.label(code), alloc.color(code), off, deg, wear, 0.3, source="manual · fill in"))
    if not out:  # nothing known about the track: generic C3/C2/C1
        for code, role in ((18, "S"), (19, "M"), (20, "H")):
            off, deg, wear = _MANUAL[role]
            out.append(CompoundSpec(code, alloc.label(code) if alloc.roles else f"{role} (generic)", alloc.color(code), off, deg, wear, 0.3, source="manual · fill in"))
    return out


def _plan_text(plan: Plan, specs: dict[int, CompoundSpec]) -> str:
    return plan.describe(specs)


def _windows_text(plan: Plan) -> str:
    parts = []
    for lap, (lo, hi) in zip(plan.stop_laps, plan.windows):
        parts.append(f"L{lap}" + (f" ({lo}–{hi})" if (lo, hi) != (lap, lap) else ""))
    return ", ".join(parts) or "no stop"


def _fmt_time(s: float) -> str:
    m, sec = divmod(float(s), 60.0)
    h, m = divmod(m, 60.0)
    return f"{int(h)}:{int(m):02d}:{sec:06.3f}" if h else f"{int(m)}:{sec:06.3f}"


def _timeline_rows(plans: list[tuple[str, Plan]], specs: dict[int, CompoundSpec], alloc: Allocation, best_time: float) -> list[dict[str, Any]]:
    rows = []
    for label, p in plans:
        lap = 1
        segs = []
        for c, n in zip(p.compounds, p.stints):
            spec = specs.get(c)
            role = alloc.role(c)
            segs.append(
                {
                    "from": lap,
                    "to": lap + n - 1,
                    "color": spec.color if spec else alloc.color(c),
                    "text": role or (spec.label if spec else str(c)),
                    "title": f"{spec.label if spec else c} · L{lap}–{lap + n - 1}",
                    "light": role == "H",
                }
            )
            lap += n
        delta = p.race_time - best_time
        rows.append({"label": label, "stints": segs, "note": "best" if abs(delta) < 1e-6 else f"{delta:+.1f} s"})
    return rows


def _no_review_reason(summary: pd.DataFrame, by_code: dict[int, CompoundSpec], params: RaceParams, state: str) -> str:
    plan = actual_plan(summary)
    if plan is None:
        return "No race review: a stint in this session has no compound logged."
    outside = sorted({c for c in plan.compounds if c not in by_code})
    if outside:
        names = ", ".join(c_label(c) for c in outside)
        return f"No race review: this race used {names}, which the {state} model does not include — pick that track state."
    if sum(plan.stints) != params.laps:
        return f"No race review: race laps are set to {params.laps} but this race ran {sum(plan.stints)}."
    return "No race review for this session."


def _params_form(params: RaceParams, key: str) -> RaceParams:
    c = st.columns(6)
    laps = c[0].number_input("Race laps", 1, 120, int(params.laps), 1, key=f"{key}_laps")
    pit = c[1].number_input("Pit loss (s)", 0.0, 60.0, float(round(params.pit_loss_s, 1)), 0.5, key=f"{key}_pit")
    fuel = c[2].number_input("Fuel burn (kg/lap)", 0.1, 5.0, float(round(params.fuel_per_lap_kg, 2)), 0.05, key=f"{key}_fuel")
    k = c[3].number_input("Fuel effect (s/kg)", 0.0, 0.2, float(params.fuel_effect_s_per_kg), 0.005, format="%.3f", key=f"{key}_k")
    wl = c[4].number_input("Wear limit (%)", 30.0, 95.0, float(wear_limit()), 1.0, key=f"{key}_wl")
    sc = c[5].number_input("SC pit loss ×", 0.1, 1.0, float(params.sc_pit_factor), 0.05, key=f"{key}_sc", help="Pit loss under safety car as a share of the green-flag loss.")
    d = st.columns(6)
    base = d[0].number_input("Base pace (s)", 30.0, 200.0, float(round(params.base_pace_s, 3)), 0.1, key=f"{key}_base", help="Reference compound, new tyre, 5 kg fuel.")
    margin = d[1].number_input("Fuel margin (laps)", 0.0, 5.0, float(params.fuel_margin_laps), 0.5, key=f"{key}_margin")
    stops = d[2].number_input("Max stops", 0, 4, int(params.max_stops), 1, key=f"{key}_stops")
    tol = d[3].number_input("Window tolerance (s)", 0.1, 10.0, float(params.window_tolerance_s), 0.5, key=f"{key}_tol")
    d[4].write("")
    two = d[4].toggle("Two dry compounds", value=bool(params.require_two_compounds), key=f"{key}_two")
    return replace(
        params,
        laps=int(laps),
        pit_loss_s=float(pit),
        fuel_per_lap_kg=float(fuel),
        fuel_effect_s_per_kg=float(k),
        wear_limit_pct=float(wl),
        sc_pit_factor=float(sc),
        base_pace_s=float(base),
        fuel_margin_laps=float(margin),
        max_stops=int(stops),
        window_tolerance_s=float(tol),
        require_two_compounds=bool(two),
    )


def _specs_editor(specs: list[CompoundSpec], notes: dict[int, str], key: str) -> list[CompoundSpec]:
    frame = pd.DataFrame(
        [
            {
                "Use": s.use,
                "Compound": s.label,
                "Offset (s)": round(s.offset_s, 3),
                "Deg (s/lap)": round(s.deg_s_per_lap, 3),
                "Wear (%/lap)": round(s.wear_pct_per_lap, 2) if s.wear_pct_per_lap else None,
                "Warm-up (s)": round(s.warmup_s, 2),
                "Source": s.source,
                "Note": notes.get(s.code, ""),
            }
            for s in specs
        ]
    )
    edited = st.data_editor(
        frame,
        hide_index=True,
        use_container_width=True,
        key=f"{key}_specs",
        disabled=["Compound", "Source", "Note"],
        column_config={
            "Offset (s)": st.column_config.NumberColumn(help="Pace vs the reference compound at the same tyre age and fuel (negative = faster).", format="%.3f"),
            "Deg (s/lap)": st.column_config.NumberColumn(help="Time lost per lap of tyre age (fuel-corrected).", format="%.3f"),
            "Wear (%/lap)": st.column_config.NumberColumn(help="Limiting-wheel wear rate; caps the stint at the wear limit.", format="%.2f"),
        },
    )
    def num(v: Any) -> float:
        return float(v) if v is not None and pd.notna(v) else 0.0

    out = []
    for s, (_, row) in zip(specs, edited.iterrows()):
        before = (round(s.offset_s, 3), round(s.deg_s_per_lap, 3), round(s.wear_pct_per_lap or 0.0, 2), round(s.warmup_s, 2))
        after = (num(row["Offset (s)"]), num(row["Deg (s/lap)"]), num(row["Wear (%/lap)"]), num(row["Warm-up (s)"]))
        changed = any(abs(a - b) > 1e-9 for a, b in zip(after, before))
        out.append(
            replace(
                s,
                use=bool(row["Use"]),
                offset_s=after[0],
                deg_s_per_lap=max(0.0, after[1]),
                wear_pct_per_lap=after[2] or None,
                warmup_s=after[3],
                source="manual" if changed else s.source,
            )
        )
    return out


def _race_trace(plans: list[Plan], specs: list[CompoundSpec], params: RaceParams, by_code: dict[int, CompoundSpec], key: str, actual: tuple[str, np.ndarray] | None = None) -> None:
    laps = np.arange(1, params.laps + 1, dtype=float)
    best = np.cumsum(lap_times(plans[0], specs, params))
    colors = ["#E03C31", "#3E7CC9", "#2E9E44", "#E8A317", "#8A6FD1"]
    gap_lines, time_lines = [], []
    for i, p in enumerate(plans[:CHART_PLANS]):
        t = lap_times(p, specs, params)
        gap_lines.append(series(p.describe(by_code), np.cumsum(t) - best, color=colors[i % len(colors)], decimals=2))
        time_lines.append(series(p.describe(by_code), t, color=colors[i % len(colors)], decimals=3))
    if actual is not None:
        label, t = actual
        gap_lines.append(series(label, np.cumsum(t) - best, color="#8A9099", dash=True, decimals=2))
        time_lines.append(series(label, t, color="#8A9099", dash=True, decimals=3, mode="points", size=5))
    markers = [{"x": float(lap), "label": "box"} for lap in plans[0].stop_laps]
    finite = np.concatenate([s["values"] for s in time_lines])
    finite = finite[np.isfinite(finite)]
    rng = [float(np.percentile(finite, 1)) - 0.5, float(np.percentile(finite, 90)) + 1.0] if finite.size else None
    trace_chart(
        laps,
        [
            pane("Gap to best plan (+ = behind)", gap_lines, unit="s", height=200, decimals=2, axis_decimals=0),
            pane("Lap time (pit loss on the in-lap)", time_lines, unit="s", height=170, decimals=3, axis_decimals=1, **({"range": rng} if rng else {})),
        ],
        key=key,
        x_label="Lap",
        markers=markers,
        sync="race",
    )


def render_strategy(
    track: str,
    state: str,
    app_root: Path,
    *,
    key: str,
    session: dict[str, Any] | None = None,
    summary: pd.DataFrame | None = None,
    df: pd.DataFrame | None = None,
) -> None:
    track_n = normalize_track_name(track) or track
    alloc = get_allocation(track_n, app_root)
    with st.spinner("Building the compound model from your library…"):
        model: TrackTyreModel = track_compound_model(track_n, state, app_root, wear_limit=wear_limit())
    specs0 = specs_from_model(model) if model.compounds else _manual_specs(alloc)
    notes = {c: m.note for c, m in model.compounds.items() if m.note}
    params0 = default_params(model, track_n)
    saved_p, saved_c = load_overrides(track_n, state, app_root)
    params0, specs0 = apply_overrides(params0, specs0, saved_p, saved_c)

    src = []
    src.append(f"sessions {', '.join(f'#{i}' for i in model.sources)}" if model.sources else "no long runs yet — manual model")
    src.append(f"pit loss measured {model.pit_loss:.1f} s" if model.pit_loss else "pit loss from track fallback")
    if saved_p or saved_c:
        src.append("saved overrides applied")
    st.caption(f"**{track_n}** · {state} · model from " + " · ".join(src))

    params = _params_form(params0, key)
    st.markdown("**Compound model** — edit any value; the plan updates immediately.")
    specs = _specs_editor(specs0, notes, key)
    b1, b2, _ = st.columns([1, 1, 3])
    if b1.button("Save as track defaults", key=f"{key}_save"):
        save_overrides(track_n, state, params, specs, app_root)
        st.success("Saved for this track and track state.")
    if b2.button("Reset to measured", key=f"{key}_reset"):
        clear_overrides(track_n, state, app_root)
        for suffix in ("laps", "pit", "fuel", "k", "wl", "sc", "base", "margin", "stops", "tol", "two", "specs"):
            st.session_state.pop(f"{key}_{suffix}", None)
        st.rerun()

    plans = optimise(specs, params)
    if not plans:
        st.warning("No feasible plan: every compound runs out before the flag at this wear limit, or the two-compound rule cannot be met.")
        return
    by_code = {s.code: s for s in specs}
    best = plans[0]

    m = st.columns(4)
    m[0].metric("Best plan", f"{best.stops}-stop", best.describe(by_code), delta_color="off", delta_arrow="off")
    m[1].metric("Race time (model)", _fmt_time(best.race_time))
    m[2].metric("Box", _windows_text(best))
    m[3].metric("Start fuel", f"{params.start_fuel_kg:.1f} kg", f"{params.fuel_per_lap_kg:.2f} kg/lap + {params.fuel_margin_laps:g} lap", delta_color="off", delta_arrow="off")

    # Best plan per stop count always shown, then the fastest others.
    shown: list[Plan] = []
    for stops in sorted({p.stops for p in plans}):
        shown.append(next(p for p in plans if p.stops == stops))
    for p in plans:
        if len(shown) >= TOP_PLANS:
            break
        if p not in shown:
            shown.append(p)
    shown.sort(key=lambda p: p.race_time)
    table = pd.DataFrame(
        [
            {
                "#": i + 1,
                "Plan": p.describe(by_code),
                "Stops": p.stops,
                "Box lap (window)": _windows_text(p),
                "Race time": _fmt_time(p.race_time),
                "Δ best (s)": round(p.race_time - best.race_time, 1),
            }
            for i, p in enumerate(shown)
        ]
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

    review = None
    actual_trace = None
    game_windows = game_pit_windows(df) if df is not None else []
    is_race = summary is not None and not summary.empty and (
        str((session or {}).get("session_type") or "") == "Race"
        or ("pit_stop" in summary.columns and bool(summary["pit_stop"].any()))
    )
    if is_race:
        review = review_race(summary, specs, params)
        if review is not None:
            # Laps the export skipped are filled from the model of the plan that was run.
            actual = lap_times(review.actual, specs, params)
            for lap, t in zip(summary["lap"].astype(int), summary["lap_time"].astype(float)):
                if 0 <= lap < len(actual):
                    actual[lap] = t
            label = "Actual" + (f" (laps {', '.join(map(str, review.missing_laps))} from model)" if review.missing_laps else "")
            actual_trace = (label, actual)

    rows = [(f"#{i + 1} {p.stops}-stop", p) for i, p in enumerate(shown[:5])]
    if review is not None:
        rows.append(("Actual (this race)", replace(review.actual, race_time=review.model_actual_time)))
    stint_timeline(_timeline_rows(rows, by_code, alloc, best.race_time), laps_total=params.laps, key=f"{key}_tl")
    st.caption("Stint order is free in this model (no fuel × compound interaction) — the softest set is listed first.")
    _race_trace(shown, specs, params, by_code, key=f"{key}_trace", actual=actual_trace)

    tab_sens, tab_calls, tab_review = st.tabs(["Sensitivity", "Pit-wall calls", "Race review"])
    with tab_sens:
        st.dataframe(sensitivity(specs, params, best), use_container_width=True, hide_index=True)
        st.caption("'Baseline plan costs' = time lost if you keep the best plan above when the scenario is the real one.")
    with tab_calls:
        calls = race_calls(best, specs, params)
        st.dataframe(calls, use_container_width=True, hide_index=True, height=360)
        st.caption(
            "Along the best plan. Negative = boxing now is faster than staying out (and boxing later at the normal loss). "
            "Undercut gain = one more lap on these tyres minus the first lap on a fresh set."
        )
    with tab_review:
        if review is None:
            st.caption(_no_review_reason(summary, by_code, params, state) if is_race else
                       "Open a race session (with pit stops) to compare the strategy that was run with the model optimum.")
        else:
            r = st.columns(4)
            r[0].metric(
                "Actual race",
                _fmt_time(review.actual_time) if review.actual_time is not None else "incomplete",
                review.actual.describe(by_code),
                delta_color="off",
                delta_arrow="off",
            )
            r[1].metric("Model of that plan", _fmt_time(review.model_actual_time))
            r[2].metric("Strategy cost", f"{review.strategy_cost_s:+.1f} s", help="Model time of the plan you ran minus the model optimum.")
            r[3].metric(
                "Execution vs model",
                f"{review.execution_s:+.1f} s" if review.execution_s is not None else "—",
                help="Actual time minus the model for the plan you ran (includes start lap, traffic, driving).",
            )
            notes = []
            if review.missing_laps:
                notes.append(
                    f"the export is missing lap(s) {', '.join(map(str, review.missing_laps))}, so the total race time is unknown"
                )
            if review.sc_laps:
                notes.append(f"safety-car lap(s) {', '.join(map(str, review.sc_laps))} are left out of the execution delta")
            for k, code, n, cap in review.over_limit:
                notes.append(
                    f"stint {k} ran {n} laps on {by_code[code].label}, past the {params.wear_limit_pct:.0f}% wear limit "
                    f"(model max {cap}) — raise the limit to compare like for like"
                )
            if notes:
                st.caption("Note: " + "; ".join(notes) + ".")
        if game_windows:
            st.caption(
                "Game's pit window during the race (ideal–latest lap): "
                + " → ".join(f"L{a}–{b}" for a, b in game_windows)
            )
