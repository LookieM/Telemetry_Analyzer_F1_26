"""Streamlit render helpers for 2026 channels + fuel/tyre windows."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from telemetry import plots
from telemetry.ers import (
    active_aero_by_distance,
    channels_2026_insights,
    lap_2026_summary,
    power_split_by_distance,
    session_2026_table,
)
from telemetry.metrics import build_lap_summary, get_lap
from telemetry.race_windows import analyze_stint_windows, stint_window_insights


def _tip_css(severity: str) -> str:
    return {"tip": "insight-tip", "warning": "insight-warning", "info": "insight-info"}.get(
        severity, "insight-info"
    )


def render_2026_channels_panel(
    df: pd.DataFrame,
    focus_lap: int,
    reference_lap: int | None = None,
    chart_prefix: str = "2026",
) -> None:
    """Active aero / overtake / ICE–MGUK KPIs + charts for the ERS tab."""
    focus_df = get_lap(df, focus_lap)
    ref_lap = reference_lap
    kpis = lap_2026_summary(focus_df)
    has_aero = "activeAero_mode" in focus_df.columns
    has_ot = "overtake" in focus_df.columns or "overtake_allowed" in focus_df.columns
    has_power = "ice_power" in focus_df.columns or "mguk_power" in focus_df.columns

    if not (has_aero or has_ot or has_power):
        st.caption("No activeAero / overtake / ICE–MGUK columns in this session export.")
        return

    st.subheader("2026 channels")
    st.caption("Active aero, overtake button, and ICE vs MGUK power split from the SRT export.")

    m1, m2, m3, m4, m5 = st.columns(5)
    if has_aero and kpis:
        m1.metric("Low-drag aero", f"{kpis.get('aero_low_drag_pct', float('nan')):.0f}%")
    else:
        m1.metric("Low-drag aero", "—")
    if has_ot and kpis:
        m2.metric("OT allowed", f"{kpis.get('overtake_allowed_pct', float('nan')):.0f}%")
        m3.metric("OT used", f"{kpis.get('overtake_used_pct', float('nan')):.0f}%")
    else:
        m2.metric("OT allowed", "—")
        m3.metric("OT used", "—")
    if has_power and kpis:
        m4.metric("MGUK share", f"{kpis.get('mguk_share_pct', float('nan')):.0f}%")
        m5.metric(
            "WOT MGUK",
            f"{kpis.get('wot_mguk_share_pct', float('nan')):.0f}%"
            if pd.notna(kpis.get("wot_mguk_share_pct"))
            else "—",
        )
    else:
        m4.metric("MGUK share", "—")
        m5.metric("WOT MGUK", "—")

    c1, c2 = st.columns(2)
    with c1:
        if has_aero:
            st.plotly_chart(
                plots.active_aero_plot(focus_df),
                use_container_width=True,
                key=f"chart_{chart_prefix}_aero_trace",
            )
            focus_prof = active_aero_by_distance(focus_df, n_bins=12)
            ref_prof = None
            if ref_lap is not None and ref_lap != focus_lap:
                ref_prof = active_aero_by_distance(get_lap(df, int(ref_lap)), n_bins=12)
            st.plotly_chart(
                plots.active_aero_profile_bars(focus_prof, ref_prof),
                use_container_width=True,
                key=f"chart_{chart_prefix}_aero_profile",
            )
        if has_ot:
            st.plotly_chart(
                plots.overtake_soc_plot(focus_df),
                use_container_width=True,
                key=f"chart_{chart_prefix}_overtake",
            )
    with c2:
        if has_power:
            power_prof = power_split_by_distance(focus_df, n_bins=12)
            st.plotly_chart(
                plots.power_split_plot(power_prof),
                use_container_width=True,
                key=f"chart_{chart_prefix}_power",
            )

        table = session_2026_table(df)
        if not table.empty:
            show = table.copy()
            for col in (
                "lap_time",
                "aero_low_drag_pct",
                "overtake_used_pct",
                "mguk_share_pct",
                "wot_mguk_share_pct",
                "ice_avg_kw",
                "mguk_avg_kw",
            ):
                if col in show.columns:
                    show[col] = show[col].map(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
            cols = [
                c
                for c in [
                    "lap",
                    "lap_time",
                    "aero_low_drag_pct",
                    "overtake_allowed_pct",
                    "overtake_used_pct",
                    "mguk_share_pct",
                    "wot_mguk_share_pct",
                    "ice_avg_kw",
                    "mguk_avg_kw",
                ]
                if c in show.columns
            ]
            st.dataframe(show[cols], use_container_width=True, hide_index=True)

    for tip in channels_2026_insights(df, focus_lap, reference_lap=ref_lap):
        st.markdown(
            f'<div class="{_tip_css(tip.severity)}"><strong>{tip.title}</strong><br/>{tip.detail}</div>',
            unsafe_allow_html=True,
        )


def render_stint_windows_panel(
    df: pd.DataFrame,
    track_length_m: float | None = None,
    default_target_laps: int | None = None,
    chart_prefix: str = "windows",
) -> None:
    """Fuel remaining-distance + tyre cliff projections for Setup / stint tab."""
    st.subheader("Fuel & tyre windows")
    st.caption("Project remaining fuel and tyre cliff from this session’s stint table.")

    summary = build_lap_summary(df)
    laps_done = int(summary["lap"].nunique()) if not summary.empty else 0
    guess = default_target_laps
    if guess is None:
        guess = max(laps_done + 5, 20) if laps_done else 20

    w1, w2, w3 = st.columns(3)
    target_laps = int(
        w1.number_input(
            "Target laps",
            min_value=1,
            max_value=100,
            value=int(guess),
            step=1,
            key=f"{chart_prefix}_target_laps",
        )
    )
    cliff = float(
        w2.number_input(
            "Tyre cliff %",
            min_value=30.0,
            max_value=90.0,
            value=55.0,
            step=1.0,
            key=f"{chart_prefix}_cliff",
        )
    )
    race_km = w3.number_input(
        "Race distance (km, optional)",
        min_value=0.0,
        max_value=400.0,
        value=0.0,
        step=1.0,
        key=f"{chart_prefix}_race_km",
    )
    race_distance_m = float(race_km) * 1000.0 if race_km and race_km > 0 else None

    windows = analyze_stint_windows(
        df,
        target_laps=target_laps,
        race_distance_m=race_distance_m,
        track_length_m=track_length_m,
        cliff_wear_pct=cliff,
        horizon_laps=min(20, max(8, target_laps - laps_done + 3)),
    )
    fuel, tyre, proj = windows.fuel, windows.tyre, windows.projection

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "Fuel left",
        f"{fuel.fuel_remaining:.1f}" if fuel.fuel_remaining is not None else "—",
    )
    k2.metric(
        "Laps in tank",
        f"{fuel.laps_possible:.1f}" if fuel.laps_possible is not None else "—",
    )
    k3.metric(
        "Laps in hand",
        f"{fuel.laps_in_hand:+.1f}" if fuel.laps_in_hand is not None else "—",
        help="Projected laps possible minus laps still needed to hit the target.",
    )
    k4.metric(
        "Laps to cliff",
        f"{tyre.laps_to_cliff:.1f}" if tyre.laps_to_cliff is not None else "—",
        tyre.cliff_risk if tyre.cliff_risk != "unknown" else None,
    )

    p1, p2 = st.columns(2)
    with p1:
        st.plotly_chart(
            plots.fuel_window_plot(summary, proj, fuel_window=fuel),
            use_container_width=True,
            key=f"chart_{chart_prefix}_fuel",
        )
    with p2:
        st.plotly_chart(
            plots.tyre_cliff_plot(summary, proj, tyre_cliff=tyre),
            use_container_width=True,
            key=f"chart_{chart_prefix}_tyre",
        )

    for tip in stint_window_insights(
        df,
        target_laps=target_laps,
        race_distance_m=race_distance_m,
        track_length_m=track_length_m,
        cliff_wear_pct=cliff,
    ):
        st.markdown(
            f'<div class="{_tip_css(tip.severity)}"><strong>[{tip.category}] {tip.title}</strong><br/>{tip.detail}</div>',
            unsafe_allow_html=True,
        )
