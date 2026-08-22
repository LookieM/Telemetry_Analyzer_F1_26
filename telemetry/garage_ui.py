"""
Shared garage tweaker helpers for standalone Garage + session Setup tab.

Formats setups in F1 26 garage units and renders the common slider / impact UI.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from telemetry import plots
from telemetry.setup_tweaker import (
    SETUP_PARAMS,
    SetupParam,
    display_value,
    estimate_setup_delta,
    estimate_to_frame,
    normalize_setup,
    setup_presets,
    storage_value,
)

GROUP_ORDER = ("Fuel", "Aero", "Transmission", "Geometry", "Suspension", "Brakes", "Tyres")


def apply_setup_to_state(state_key: str, ui_id: str, values: dict[str, Any]) -> None:
    """Write a setup dict into session_state and sync slider widgets."""
    normed = normalize_setup(values) if values else {}
    # Keep any non-SETUP_PARAMS keys, but prefer clamped known params
    merged = {**dict(values), **normed}
    if "brake_bias_setup" in merged and "front_brake_bias" in merged:
        merged["front_brake_bias"] = merged["brake_bias_setup"]
    st.session_state[state_key] = merged
    for param in SETUP_PARAMS:
        if param.key not in merged:
            continue
        lo = display_value(param, param.min_v)
        hi = display_value(param, param.max_v)
        disp = display_value(param, merged[param.key])
        st.session_state[f"setup_sl_{ui_id}_{param.key}"] = float(min(max(disp, lo), hi))


def format_param_display(param: SetupParam, value: float) -> str:
    """Human-readable garage value for the copy card."""
    disp = display_value(param, value)
    unit = (param.unit or "").strip()
    if unit in ("%", "% front"):
        return f"{disp:.0f}%"
    if unit == "psi":
        return f"{disp:.2f} psi"
    if unit == "°":
        return f"{disp:.2f}°"
    if unit == "kg":
        return f"{disp:.0f} kg"
    if abs(disp - round(disp)) < 1e-6:
        return f"{disp:.0f}"
    return f"{disp:.2f}"


def setup_copy_frame(setup: dict[str, Any]) -> pd.DataFrame:
    """One row per garage param in game units (for dialling into F1 26)."""
    norm = normalize_setup(setup)
    rows = []
    for param in SETUP_PARAMS:
        if param.key not in norm:
            continue
        # Hide live bias duplicate when setup bias is present
        if param.key == "front_brake_bias" and "brake_bias_setup" in norm:
            continue
        rows.append(
            {
                "Group": param.group,
                "Parameter": param.label,
                "Value": format_param_display(param, norm[param.key]),
            }
        )
    return pd.DataFrame(rows)


def _format_display_num(param: SetupParam, storage: float) -> str:
    disp = display_value(param, storage)
    unit = (param.unit or "").strip()
    if unit in ("%", "% front"):
        return f"{disp:.0f}"
    if unit in ("psi", "°"):
        return f"{disp:.2f}"
    if abs(disp - round(disp)) < 1e-6:
        return f"{disp:.0f}"
    return f"{disp:.3g}"


def impact_frame_display(est) -> pd.DataFrame:
    """Impact table in garage display units (psi / % / clicks), not storage."""
    frame = estimate_to_frame(est)
    if frame.empty:
        return frame
    pmap = {p.key: p for p in SETUP_PARAMS}
    rows = []
    for ln in est.lines:
        param = pmap.get(ln.key)
        if param is None:
            rows.append(
                {
                    "Parameter": ln.label,
                    "Baseline": ln.baseline,
                    "Proposed": ln.proposed,
                    "Δ units": f"{ln.delta_units:+.3g}",
                    "Est. Δt (s)": f"{ln.est_dt:+.3f}",
                    "Note": ln.note,
                }
            )
            continue
        base_d = display_value(param, ln.baseline)
        prop_d = display_value(param, ln.proposed)
        delta_d = prop_d - base_d
        unit = (param.unit or "").strip()
        delta_label = f"{delta_d:+.2f}" if unit in ("psi", "°") else f"{delta_d:+.3g}"
        rows.append(
            {
                "Parameter": ln.label,
                "Baseline": _format_display_num(param, ln.baseline),
                "Proposed": _format_display_num(param, ln.proposed),
                "Δ units": delta_label,
                "Est. Δt (s)": f"{ln.est_dt:+.3f}",
                "Note": ln.note,
            }
        )
    return pd.DataFrame(rows)


def render_garage_tweaker(
    *,
    ui_id: str,
    state_key: str,
    compare_base: dict[str, float],
    track: str | None,
    reference_lap_time: float | None = None,
    base_label: str = "baseline",
    chart_prefix: str = "garage",
    conditions: str | None = None,
) -> dict[str, float]:
    """
    Render presets, sliders, Δt estimate, and proposed metrics.
    Returns the current proposed setup dict.
    """
    if not compare_base and not st.session_state.get(state_key):
        st.info("Load a typical track setup to start.")
        return {}

    if not st.session_state.get(state_key) and compare_base:
        st.session_state[state_key] = dict(compare_base)

    proposed = dict(st.session_state.get(state_key) or {})
    # Ensure all SETUP_PARAMS keys exist when we have a full compare base
    for k, v in compare_base.items():
        proposed.setdefault(k, v)

    # Presets must start from current proposed (not baseline), so sliders aren't wiped
    presets = setup_presets(proposed, conditions=conditions) if proposed else {}
    if presets:
        pcols = st.columns(min(4, max(1, len(presets))))
        for i, (name, preset) in enumerate(presets.items()):
            if pcols[i % len(pcols)].button(name, key=f"preset_{ui_id}_{i}"):
                apply_setup_to_state(state_key, ui_id, preset)
                st.rerun()

    proposed = dict(st.session_state.get(state_key) or proposed)
    active_keys = set(proposed) | set(compare_base)
    groups: dict[str, list] = {}
    for param in SETUP_PARAMS:
        if param.key not in active_keys:
            continue
        if param.key == "front_brake_bias" and "brake_bias_setup" in active_keys:
            continue
        groups.setdefault(param.group, []).append(param)

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("Garage tweaker")
        for group in GROUP_ORDER:
            params = groups.get(group) or []
            if not params:
                continue
            with st.expander(group, expanded=group in ("Aero", "Suspension", "Brakes", "Tyres")):
                for param in params:
                    cur = proposed.get(param.key, compare_base.get(param.key, param.min_v))
                    disp = display_value(param, cur)
                    lo = display_value(param, param.min_v)
                    hi = display_value(param, param.max_v)
                    step = float(param.step) * float(param.display_scale)
                    if step <= 0:
                        step = 1.0
                    slider_key = f"setup_sl_{ui_id}_{param.key}"
                    if slider_key not in st.session_state:
                        st.session_state[slider_key] = float(min(max(disp, lo), hi))
                    new_disp = st.slider(
                        f"{param.label} ({param.unit})" if param.unit else param.label,
                        min_value=float(lo),
                        max_value=float(hi),
                        step=float(step),
                        key=slider_key,
                        help=param.notes or None,
                    )
                    proposed[param.key] = storage_value(param, new_disp)
                    if param.key == "brake_bias_setup" and "front_brake_bias" in active_keys:
                        proposed["front_brake_bias"] = proposed[param.key]
        st.session_state[state_key] = proposed

    est = estimate_setup_delta(
        compare_base,
        proposed,
        track=track,
        reference_lap_time=reference_lap_time,
        conditions=conditions,
    )
    with right:
        st.subheader("Estimated impact")
        if abs(est.total_dt) < 5e-4:
            delta_caption = f"unchanged vs {base_label}"
        else:
            verb = "faster" if est.total_dt < 0 else "slower"
            delta_caption = f"{abs(est.total_dt):.3f}s {verb} than {base_label}"
        st.metric(
            "Net estimated Δt",
            f"{est.total_dt:+.3f} s",
            delta_caption,
        )
        st.caption(est.confidence)
        st.info(est.aero_balance_note)
        show = impact_frame_display(est)
        if not show.empty:
            raw_frame = estimate_to_frame(est)
            st.plotly_chart(
                plots.setup_delta_bars(raw_frame),
                use_container_width=True,
                key=f"chart_{chart_prefix}_delta",
            )
            st.plotly_chart(
                plots.setup_breakdown_pie(est.breakdown),
                use_container_width=True,
                key=f"chart_{chart_prefix}_break",
            )
            st.dataframe(show, use_container_width=True, hide_index=True)
        else:
            st.write("Move a slider or load a typical setup to see estimated impact.")

        st.subheader("Proposed card")
        m1, m2, m3, m4 = st.columns(4)
        bias_setup = proposed.get("brake_bias_setup")
        bias_live = proposed.get("front_brake_bias")
        bias_val = bias_setup if bias_setup is not None else bias_live
        bias_shown = (float(bias_val) if bias_val is not None else 0.0) * 100
        m1.metric("FW / RW", f"{proposed.get('wing_setup_0', 0):.0f} / {proposed.get('wing_setup_1', 0):.0f}")
        m2.metric("Bias", f"{bias_shown:.0f}%")
        m3.metric("Fuel", f"{proposed.get('fuel_setup', 0):.0f} kg")
        m4.metric("ARB F/R", f"{proposed.get('arb_setup_0', 0):.0f}/{proposed.get('arb_setup_1', 0):.0f}")

        st.subheader("Copy into game")
        card = setup_copy_frame(proposed)
        if not card.empty:
            st.dataframe(card, use_container_width=True, hide_index=True, height=360)
            st.caption("Values match F1 26 garage units (psi, %, degrees, clicks).")

    return proposed
