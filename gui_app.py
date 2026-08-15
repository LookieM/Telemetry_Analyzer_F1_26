"""
F1 26 Telemetry Analyzer — Streamlit UI

Session library + track dossier / PB history + Bahrain corners +
graph↔map position cursor (click / scrub).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from telemetry import plots
from telemetry.corners import (
    analyze_lap_corners,
    compare_corners,
    corner_at_distance,
    list_supported_tracks,
    normalize_track_name,
    resolve_corners,
)
from telemetry.db import (
    delete_session,
    get_session,
    get_session_laps,
    get_track_outline,
    init_db,
    library_stats,
    list_sessions,
    list_tracks,
    load_session_telemetry,
    update_session_notes,
)
from telemetry.ers import (
    ers_by_corner,
    ers_by_distance,
    lap_ers_summary,
    practice_ers_insights,
    recommended_deploy_map,
    session_ers_table,
)
from telemetry.track_catalog import TRACK_LENGTHS_M
from telemetry.import_session import import_csv
from telemetry.insights import Insight, generate_insights
from telemetry.loader import list_local_csvs
from telemetry.metrics import (
    align_laps,
    build_lap_summary,
    compute_time_delta,
    get_lap,
    sector_deltas,
    setup_snapshot,
)
from telemetry.progress import (
    backfill_progress_from_library,
    ensure_progress_schema,
    get_track_goal,
    set_track_goal,
    track_dossier,
)
from telemetry.setup_builder import build_setup_from_practice, changes_frame
from telemetry.setup_tweaker import (
    SETUP_PARAMS,
    display_value,
    estimate_setup_delta,
    estimate_to_frame,
    normalize_setup,
    pa_to_psi,
    setup_presets,
    storage_value,
)
from telemetry.stint_coach import session_stint_table, stint_saving_insights
from telemetry.track_setups import get_typical_setup, list_tracks_with_setups

st.set_page_config(
    page_title="F1 26 Telemetry Analyzer",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.2rem; }
    div[data-testid="stMetricValue"] { font-size: 1.4rem; }
    .insight-tip { border-left: 3px solid #38bdf8; padding: 0.4rem 0.8rem; margin: 0.4rem 0; background: rgba(56,189,248,0.08); }
    .insight-warning { border-left: 3px solid #f59e0b; padding: 0.4rem 0.8rem; margin: 0.4rem 0; background: rgba(245,158,11,0.08); }
    .insight-info { border-left: 3px solid #6b7280; padding: 0.4rem 0.8rem; margin: 0.4rem 0; background: rgba(107,114,128,0.08); }
    </style>
    """,
    unsafe_allow_html=True,
)

APP_ROOT = Path(__file__).resolve().parent


@st.cache_data(show_spinner=False)
def cached_session_df(session_id: int, telemetry_path: str, stored_size: int) -> pd.DataFrame:
    return load_session_telemetry(session_id, APP_ROOT)


def format_lap_time(seconds: float | None) -> str:
    if seconds is None or (isinstance(seconds, float) and pd.isna(seconds)):
        return "—"
    seconds = float(seconds)
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:06.3f}" if m else f"{s:.3f}s"


def format_bytes(n: int | float | None) -> str:
    if n is None:
        return "—"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def render_insights(items: list[Insight] | list[dict]) -> None:
    for item in items:
        if isinstance(item, dict):
            severity, title, detail = item.get("severity", "info"), item.get("title", ""), item.get("detail", "")
        else:
            severity, title, detail = item.severity, item.title, item.detail
        css = {
            "tip": "insight-tip",
            "warning": "insight-warning",
            "info": "insight-info",
        }.get(severity, "insight-info")
        st.markdown(
            f'<div class="{css}"><strong>{title}</strong><br/>{detail}</div>',
            unsafe_allow_html=True,
        )


def distance_from_plotly_event(event) -> float | None:
    """Extract lap distance from a Streamlit plotly selection event."""
    if event is None:
        return None
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    if selection is None:
        return None
    points = getattr(selection, "points", None)
    if points is None and isinstance(selection, dict):
        points = selection.get("points")
    if not points:
        return None
    p = points[0]
    if isinstance(p, dict):
        cd = p.get("customdata")
        if isinstance(cd, (list, tuple)) and cd:
            try:
                return float(cd[0])
            except (TypeError, ValueError):
                pass
        if p.get("x") is not None:
            try:
                return float(p["x"])
            except (TypeError, ValueError):
                return None
    else:
        cd = getattr(p, "customdata", None)
        if isinstance(cd, (list, tuple)) and cd:
            try:
                return float(cd[0])
            except (TypeError, ValueError):
                pass
        x = getattr(p, "x", None)
        if x is not None:
            try:
                return float(x)
            except (TypeError, ValueError):
                return None
    return None


def sidebar_import() -> None:
    st.subheader("Import SRT CSV")
    local = list_local_csvs(APP_ROOT)
    src = st.radio("Source", ["Project folder", "Upload", "Custom path"], horizontal=True, key="import_src")
    path: Path | None = None

    if src == "Project folder":
        if local:
            choice = st.selectbox("CSV file", [p.name for p in local])
            path = APP_ROOT / choice
            st.caption(f"Size on disk: {format_bytes(path.stat().st_size)}")
        else:
            st.info("No CSV files in the project folder.")
    elif src == "Upload":
        up = st.file_uploader("SRT export", type=["csv", "tsv", "txt"])
        if up is not None:
            uploaded_tmp = APP_ROOT / "data" / "_import_upload.csv"
            uploaded_tmp.parent.mkdir(parents=True, exist_ok=True)
            uploaded_tmp.write_bytes(up.getvalue())
            path = uploaded_tmp
            st.caption(f"Upload size: {format_bytes(len(up.getvalue()))}")
    else:
        custom = st.text_input("Full path to CSV")
        if custom and Path(custom).exists():
            path = Path(custom)
            st.caption(f"Size: {format_bytes(path.stat().st_size)}")

    delete_src = st.checkbox(
        "Delete CSV after successful import",
        value=True,
        help="Keeps only the compact library copy.",
    )
    notes = st.text_input("Session notes (optional)", placeholder="Bahrain race — softs…")

    if st.button("Import into library", type="primary", disabled=path is None):
        assert path is not None
        with st.spinner("Importing & compressing…"):
            try:
                result = import_csv(path, app_root=APP_ROOT, delete_source=delete_src, notes=notes)
                st.success(result.message)
                st.session_state["selected_session_id"] = result.session_id
                st.cache_data.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"Import failed: {exc}")


def pick_session() -> dict | None:
    sessions = list_sessions(APP_ROOT)
    if sessions.empty:
        st.info("Library is empty. Import an SRT CSV from the sidebar.")
        return None

    tracks = ["All tracks"] + list_tracks(APP_ROOT)
    track_filter = st.selectbox("Filter track", tracks, key="browse_track_filter")
    view = sessions if track_filter == "All tracks" else sessions[sessions["track"] == track_filter]

    labels = []
    ids = []
    for _, row in view.iterrows():
        best = format_lap_time(float(row["best_lap_time"])) if pd.notna(row["best_lap_time"]) else "—"
        labels.append(
            f"#{row['id']} · {row.get('track') or '?'} · {row.get('car') or '?'} · "
            f"{int(row['lap_count'])} laps · best {best} · {format_bytes(row.get('stored_size_bytes'))}"
        )
        ids.append(int(row["id"]))

    default_id = st.session_state.get("selected_session_id")
    index = ids.index(default_id) if default_id in ids else 0
    choice = st.selectbox("Session", range(len(ids)), format_func=lambda i: labels[i], index=index)
    session_id = ids[choice]
    st.session_state["selected_session_id"] = session_id
    return get_session(session_id, APP_ROOT)


def render_dossier() -> None:
    tracks_raced = list_tracks(APP_ROOT)
    catalog = list_supported_tracks()
    options = sorted(set(tracks_raced) | set(catalog))
    if not options:
        st.info("No tracks available.")
        return

    # Prefer a raced track if any
    default_idx = options.index(tracks_raced[0]) if tracks_raced and tracks_raced[0] in options else 0
    track = st.selectbox("Track", options, index=default_idx, key="dossier_track")
    has_outline = get_track_outline(track, APP_ROOT) is not None
    in_library = track in tracks_raced

    a1, a2, a3 = st.columns(3)
    a1.metric("In catalog", "Yes" if track in catalog else "Auto-detect")
    a2.metric("Sessions logged", "Yes" if in_library else "Not yet")
    a3.metric("Race map", "Saved" if has_outline else "Race once to learn outline")

    with st.expander("Track atlas — all circuits with named turns", expanded=not in_library):
        atlas_rows = []
        for name in catalog:
            outline = get_track_outline(name, APP_ROOT)
            atlas_rows.append(
                {
                    "Track": name,
                    "Length (m)": TRACK_LENGTHS_M.get(name, "—"),
                    "Named segments": len(resolve_corners(name, TRACK_LENGTHS_M.get(name))),
                    "Map learned": "Yes" if outline else "—",
                    "Your sessions": "Yes" if name in tracks_raced else "—",
                }
            )
        st.dataframe(pd.DataFrame(atlas_rows), use_container_width=True, hide_index=True)
        st.caption(
            "Maps are learned from your racing line when you import a session — "
            "turn names are ready for every catalog circuit beforehand."
        )
        preview = st.selectbox("Preview corner list", catalog, index=catalog.index(track) if track in catalog else 0)
        preview_corners = resolve_corners(preview, TRACK_LENGTHS_M.get(preview))
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "id": c.id,
                        "name": c.name,
                        "kind": c.kind,
                        "start %": f"{100 * c.start / (TRACK_LENGTHS_M.get(preview) or 1):.1f}",
                        "end %": f"{100 * c.end / (TRACK_LENGTHS_M.get(preview) or 1):.1f}",
                    }
                    for c in preview_corners
                ]
            ),
            use_container_width=True,
            hide_index=True,
            height=280,
        )

    if not in_library:
        st.info(f"Import an SRT session from **{track}** to unlock PB history, consistency, and the race map outline.")
        return

    dossier = track_dossier(track, APP_ROOT)
    goal = dossier.get("goal")
    outline = get_track_outline(track, APP_ROOT)

    if outline:
        st.plotly_chart(
            plots.track_library_map(outline, title=f"{track} — learned racing line"),
            use_container_width=True,
            key="dossier_outline",
        )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Personal best", format_lap_time(dossier.get("best_time")))
    c2.metric("Sessions", dossier["session_count"])
    if dossier.get("consistency"):
        c3.metric("Consistency σ", f"{dossier['consistency']['std']:.3f}s")
        c4.metric("Recent spread", f"{dossier['consistency']['spread']:.3f}s")
    else:
        c3.metric("Consistency σ", "—")
        c4.metric("Recent spread", "—")

    g1, g2 = st.columns([2, 1])
    with g1:
        default_goal = float(goal["target_lap_time"]) if goal else (float(dossier["best_time"]) - 0.5 if dossier.get("best_time") else 90.0)
        target = st.number_input("Goal lap time (seconds)", min_value=40.0, max_value=200.0, value=float(default_goal), step=0.1)
        goal_notes = st.text_input("Goal notes", value=(goal or {}).get("notes") or "")
        if st.button("Save goal"):
            set_track_goal(track, target, goal_notes, APP_ROOT)
            st.success("Goal saved.")
            st.rerun()
    with g2:
        if goal and dossier.get("best_time"):
            gap = float(dossier["best_time"]) - float(goal["target_lap_time"])
            st.metric("Gap to goal", f"{gap:+.3f}s", help="Negative means you already beat the goal.")
        st.caption("Goals are stored in the local DB and survive CSV deletion.")

    left, right = st.columns(2)
    with left:
        st.plotly_chart(plots.pb_history_chart(dossier["pb_history"]), use_container_width=True, key="dossier_pb")
    with right:
        st.plotly_chart(plots.session_bests_chart(dossier["sessions"]), use_container_width=True, key="dossier_sessions")

    st.subheader("Visit history")
    sess = dossier["sessions"].copy()
    if not sess.empty:
        show = sess[["id", "created_at", "car", "lap_count", "best_lap_time", "source_name", "notes"]].copy()
        show["best_lap_time"] = show["best_lap_time"].map(format_lap_time)
        st.dataframe(show, use_container_width=True, hide_index=True)

    st.subheader("Corner dossier (latest session best vs lifetime PB)")
    trend = dossier.get("corner_trend")
    if isinstance(trend, pd.DataFrame) and not trend.empty and "delta_vs_pb" in trend.columns:
        st.plotly_chart(
            plots.corner_delta_bars(
                trend.assign(kind="corner", delta_s=trend["delta_vs_pb"], corner_id=trend["corner_id"])
            ),
            use_container_width=True,
            key="dossier_corner_trend",
        )
        worst = trend.sort_values("delta_vs_pb", ascending=False).head(3)
        for _, row in worst.iterrows():
            if pd.notna(row.get("delta_vs_pb")) and row["delta_vs_pb"] > 0.01:
                st.markdown(
                    f"- **{row['corner_name']}**: {row['delta_vs_pb']:+.3f}s vs PB reference"
                )
    elif dossier.get("latest_corners"):
        st.caption("Only one PB snapshot so far — corner vs-PB appears after your next faster/slower visit.")
        latest = pd.DataFrame(dossier["latest_corners"])
        if not latest.empty:
            st.dataframe(
                latest[["corner_id", "corner_name", "time_s", "vmin"]].assign(
                    time_s=lambda d: d["time_s"].map(lambda x: f"{x:.3f}" if pd.notna(x) else "—"),
                    vmin=lambda d: d["vmin"].map(lambda x: f"{x:.0f}" if pd.notna(x) else "—"),
                ),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("Corner data will appear after progress backfill / next import.")


def render_analysis(session: dict, df: pd.DataFrame, summary: pd.DataFrame, outline: dict | None) -> None:
    best_lap = int(summary.loc[summary["is_best"], "lap"].iloc[0])
    laps = summary["lap"].tolist()
    track = normalize_track_name(session.get("track"))
    track_length = float(df["trackLength"].iloc[0]) if "trackLength" in df.columns else (
        float(session["track_length"]) if session.get("track_length") else None
    )
    # trackLength may not be in compact parquet — use max distance
    if track_length is None and "lap_distance" in df.columns:
        track_length = float(df["lap_distance"].max())
    corners = resolve_corners(track, track_length, get_lap(df, best_lap))

    with st.sidebar:
        st.markdown("---")
        st.subheader("Lap selection")
        focus_lap = st.selectbox(
            "Focus lap",
            laps,
            index=laps.index(best_lap),
            format_func=lambda L: f"Lap {L} — {format_lap_time(float(summary.loc[summary.lap == L, 'lap_time'].iloc[0]))}"
            + (" ★" if L == best_lap else ""),
        )
        ref_lap = st.selectbox(
            "Reference lap",
            laps,
            index=laps.index(best_lap),
            format_func=lambda L: f"Lap {L} — {format_lap_time(float(summary.loc[summary.lap == L, 'lap_time'].iloc[0]))}",
        )
        map_color = st.selectbox("Map colour", ["speed", "throttle", "brake", "delta"], index=0)

        st.markdown("---")
        st.subheader("Lap cursor")
        st.caption("Click a point on a telemetry graph, or scrub distance — the red marker shows where you are on track.")
        max_dist = float(track_length or 5408)
        if "cursor_distance" not in st.session_state:
            st.session_state["cursor_distance"] = 0.0
        st.slider("Distance (m)", 0.0, max_dist, step=1.0, key="cursor_distance")

    cursor = float(st.session_state.get("cursor_distance", 0.0))
    corner_here = corner_at_distance(track, cursor, track_length, corners=corners)

    focus_row = summary.loc[summary["lap"] == focus_lap].iloc[0]
    best_time = float(summary["lap_time"].min())
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Focus lap", format_lap_time(float(focus_row["lap_time"])), f"{focus_row['delta_best']:+.3f}s vs best")
    c2.metric("Best lap", f"#{best_lap} · {format_lap_time(best_time)}")
    c3.metric("Vmax", f"{focus_row.get('vmax', float('nan')):.1f} km/h" if pd.notna(focus_row.get("vmax")) else "—")
    c4.metric("Cursor", f"{cursor:.0f} m")
    c5.metric("At corner", corner_here.name if corner_here else "—")

    focus_df = get_lap(df, focus_lap)
    ref_df = get_lap(df, ref_lap)
    aligned = compute_time_delta(align_laps(ref_df, focus_df)) if focus_lap != ref_lap else pd.DataFrame()
    sectors = sector_deltas(aligned, n_sectors=3) if not aligned.empty else pd.DataFrame()
    mini = sector_deltas(aligned, n_sectors=12) if not aligned.empty else pd.DataFrame()

    focus_corners = analyze_lap_corners(focus_df, track, track_length, corners=corners)
    ref_corners = analyze_lap_corners(ref_df, track, track_length, corners=corners)
    corner_cmp = compare_corners(focus_corners, ref_corners)

    tabs = st.tabs(
        [
            "Session",
            "Race map",
            "Corners",
            "Lap compare",
            "Single lap",
            "Tyres",
            "ERS / 2026",
            "Setup / Stint",
            "Coach",
        ]
    )
    tab_overview, tab_map, tab_corners, tab_compare, tab_single, tab_tyres, tab_ers, tab_setup, tab_coach = tabs

    with tab_overview:
        left, right = st.columns([1.4, 1])
        with left:
            st.plotly_chart(plots.pace_chart(summary), use_container_width=True, key="chart_pace")
            st.plotly_chart(plots.fuel_tyre_stint(summary), use_container_width=True, key="chart_stint")
        with right:
            st.subheader("Storage")
            st.write(
                f"Original CSV **{format_bytes(session.get('original_size_bytes'))}** → "
                f"library **{format_bytes(session.get('stored_size_bytes'))}**"
            )
            notes = st.text_area("Notes", value=session.get("notes") or "", height=100)
            if st.button("Save notes"):
                update_session_notes(int(session["id"]), notes, APP_ROOT)
                st.success("Saved.")
            show = summary.copy()
            show["lap_time"] = show["lap_time"].map(lambda x: f"{x:.3f}")
            show["delta_best"] = show["delta_best"].map(lambda x: f"{x:+.3f}")
            cols = [c for c in ["lap", "lap_time", "delta_best", "vmax", "throttle_full_pct", "coast_pct", "fuel_used", "tyre_wear_avg", "compound", "lockup_samples"] if c in show.columns]
            st.dataframe(show[cols], use_container_width=True, hide_index=True)

    with tab_map:
        color = "speed" if map_color == "delta" else map_color
        m1, m2 = st.columns([1.2, 1])
        with m1:
            st.plotly_chart(
                plots.track_map(
                    focus_df,
                    color=color,
                    title=f"{track or 'Track'} — lap {focus_lap}",
                    outline=outline,
                    highlight_distance=cursor,
                    corners=corners,
                ),
                use_container_width=True,
                key="chart_race_map_lap",
            )
        with m2:
            st.plotly_chart(
                plots.track_library_map(outline, title=f"{track or 'Track'} outline"),
                use_container_width=True,
                key="chart_race_map_outline",
            )
            if corner_here:
                st.info(f"**{corner_here.name}** · {corner_here.start:.0f}–{corner_here.end:.0f} m")

    with tab_corners:
        if focus_corners.empty:
            st.warning("No corners available for this track yet.")
        else:
            source = "catalog" if normalize_track_name(track) in list_supported_tracks() else "auto-detected from this lap"
            st.caption(f"Corner model: **{source}**. Positive Δ = slower than reference.")
            st.plotly_chart(
                plots.corner_delta_bars(corner_cmp if focus_lap != ref_lap else focus_corners.assign(delta_s=0.0)),
                use_container_width=True,
                key="chart_corner_bars",
            )
            table = corner_cmp.copy() if focus_lap != ref_lap else focus_corners.copy()
            for col in ("time_s", "ref_time_s", "delta_s", "vmin", "ref_vmin"):
                if col in table.columns:
                    table[col] = table[col].map(lambda x: f"{x:.3f}" if pd.notna(x) else "—")
            st.dataframe(table, use_container_width=True, hide_index=True)
            if focus_lap != ref_lap and not corner_cmp.empty and "delta_s" in corner_cmp.columns:
                worst = corner_cmp[corner_cmp["kind"] == "corner"].sort_values("delta_s", ascending=False).head(3)
                st.subheader("Biggest losses")
                for _, row in worst.iterrows():
                    if pd.notna(row.get("delta_s")):
                        st.markdown(f"- **{row['corner_name']}**: {row['delta_s']:+.3f}s")

    with tab_compare:
        if focus_lap == ref_lap:
            st.info("Pick a different reference lap to see deltas and overlays.")
        else:
            final_delta = float(aligned["delta_time"].iloc[-1]) if not aligned.empty else 0.0
            st.markdown(
                f"**Lap {focus_lap}** vs **Lap {ref_lap}** → "
                f"{abs(final_delta):.3f}s {'slower' if final_delta > 0 else 'faster'}"
            )
            m1, m2 = st.columns(2)
            with m1:
                if map_color == "delta" and not aligned.empty:
                    st.plotly_chart(
                        plots.delta_map(aligned, outline=outline),
                        use_container_width=True,
                        key="chart_compare_delta_map",
                    )
                else:
                    color = map_color if map_color != "delta" else "speed"
                    st.plotly_chart(
                        plots.track_map(
                            focus_df,
                            color=color,
                            title=f"Lap {focus_lap}",
                            outline=outline,
                            highlight_distance=cursor,
                            corners=corners,
                        ),
                        use_container_width=True,
                        key="chart_compare_track_map",
                    )
            with m2:
                st.plotly_chart(plots.sector_bar(sectors), use_container_width=True, key="chart_compare_sectors")
                if not mini.empty:
                    st.dataframe(
                        mini.assign(
                            delta_s=mini["delta_s"].map(lambda x: f"{x:+.3f}"),
                            dist_start=mini["dist_start"].map(lambda x: f"{x:.0f}"),
                            dist_end=mini["dist_end"].map(lambda x: f"{x:.0f}"),
                        ),
                        use_container_width=True,
                        hide_index=True,
                        height=280,
                    )
            event = st.plotly_chart(
                plots.telemetry_overlay(
                    aligned, f"L{ref_lap}", f"L{focus_lap}", corners=corners, highlight_distance=cursor
                ),
                use_container_width=True,
                key="chart_compare_overlay",
                on_select="rerun",
                selection_mode="points",
            )
            picked = distance_from_plotly_event(event)
            if picked is not None and abs(picked - float(st.session_state.get("cursor_distance", 0.0))) > 0.75:
                st.session_state["cursor_distance"] = float(picked)
                st.rerun()

    with tab_single:
        col_a, col_b = st.columns([1.1, 1.4])
        with col_a:
            color = "speed" if map_color == "delta" else map_color
            st.plotly_chart(
                plots.track_map(
                    focus_df,
                    color=color,
                    title=f"Lap {focus_lap}",
                    outline=outline,
                    highlight_distance=cursor,
                    corners=corners,
                ),
                use_container_width=True,
                key="chart_single_track_map",
            )
            st.plotly_chart(plots.gg_diagram(focus_df), use_container_width=True, key="chart_single_gg")
        with col_b:
            event = st.plotly_chart(
                plots.single_lap_telemetry(focus_df, corners=corners, highlight_distance=cursor),
                use_container_width=True,
                key="chart_single_telemetry",
                on_select="rerun",
                selection_mode="points",
            )
            picked = distance_from_plotly_event(event)
            if picked is not None and abs(picked - float(st.session_state.get("cursor_distance", 0.0))) > 0.75:
                st.session_state["cursor_distance"] = float(picked)
                st.rerun()
            st.caption("Hover shows distance + corner name. Click a point to pin the red marker on the map.")

    with tab_tyres:
        t1, t2 = st.columns([1.5, 1])
        with t1:
            st.plotly_chart(plots.tyre_temps_plot(focus_df), use_container_width=True, key="chart_tyre_temps")
        with t2:
            st.plotly_chart(plots.tyre_wear_bars(focus_df), use_container_width=True, key="chart_tyre_wear")
        if all(f"tyre_press_{i}" in focus_df.columns for i in range(4)):
            pcols = st.columns(4)
            for i, lab in enumerate(["RL", "RR", "FL", "FR"]):
                raw = float(focus_df[f"tyre_press_{i}"].mean())
                # SRT live pressures are Pascals; show psi to match the garage
                psi = pa_to_psi(raw) if raw > 5000 else raw
                pcols[i].metric(lab, f"{psi:.1f} psi")

    with tab_ers:
        st.caption(
            "2026-focused energy analysis from this session’s practice/race laps — "
            "where you spend, where you harvest, and how SOC related to pace."
        )
        ers_table = session_ers_table(df)
        focus_ers = lap_ers_summary(focus_df)
        focus_profile = ers_by_distance(focus_df, n_bins=12)
        corner_ers = ers_by_corner(focus_df, track, track_length)
        advice = recommended_deploy_map(df, track, track_length)

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Start SOC", f"{focus_ers.get('start_mj', float('nan')):.2f} MJ" if focus_ers else "—")
        k2.metric("End SOC", f"{focus_ers.get('end_mj', float('nan')):.2f} MJ" if focus_ers else "—")
        k3.metric("Deployed", f"{focus_ers.get('deployed_mj', float('nan')):.2f} MJ" if focus_ers else "—")
        k4.metric("Harvested", f"{focus_ers.get('harvested_mj', float('nan')):.2f} MJ" if focus_ers else "—")
        k5.metric("Deploy mode", f"{focus_ers.get('deploy_mode_pct', float('nan')):.0f}%" if focus_ers else "—")

        r1, r2 = st.columns(2)
        with r1:
            st.plotly_chart(plots.ers_plot(focus_df), use_container_width=True, key="chart_ers_trace")
            st.plotly_chart(
                plots.ers_profile_bars(focus_profile, title=f"Lap {focus_lap} — deploy vs harvest"),
                use_container_width=True,
                key="chart_ers_profile",
            )
        with r2:
            st.plotly_chart(
                plots.ers_session_scatter(ers_table),
                use_container_width=True,
                key="chart_ers_scatter",
            )
            st.plotly_chart(
                plots.ers_advice_map(advice, outline_lap=focus_df),
                use_container_width=True,
                key="chart_ers_advice_map",
            )

        if not corner_ers.empty:
            st.plotly_chart(plots.ers_corner_bars(corner_ers), use_container_width=True, key="chart_ers_corners")

        st.subheader("Practice lap ERS table")
        if not ers_table.empty:
            show = ers_table.copy()
            for col in ("lap_time", "start_mj", "end_mj", "deployed_mj", "harvested_mj", "delta_best"):
                if col in show.columns:
                    show[col] = show[col].map(lambda x: f"{x:.3f}" if pd.notna(x) else "—")
            cols = [
                c
                for c in [
                    "lap",
                    "lap_time",
                    "delta_best",
                    "start_mj",
                    "end_mj",
                    "deployed_mj",
                    "harvested_mj",
                    "deploy_mode_pct",
                    "partial_throttle_deploy_pct",
                    "empty_pct",
                    "ers_discipline",
                ]
                if c in show.columns
            ]
            st.dataframe(show[cols], use_container_width=True, hide_index=True)

        st.subheader("ERS coach (from this session)")
        ers_tips = practice_ers_insights(
            df,
            focus_lap,
            reference_lap=ref_lap,
            track=track,
            track_length=track_length,
        )
        for tip in ers_tips:
            css = {"tip": "insight-tip", "warning": "insight-warning", "info": "insight-info"}.get(
                tip.severity, "insight-info"
            )
            st.markdown(
                f'<div class="{css}"><strong>{tip.title}</strong><br/>{tip.detail}</div>',
                unsafe_allow_html=True,
            )

        if "fuel" in focus_df.columns or "drs" in focus_df.columns:
            st.markdown("---")
            f1, f2, f3 = st.columns(3)
            if "fuel" in focus_df.columns:
                f1.metric("Fuel used", f"{focus_df['fuel'].iloc[0] - focus_df['fuel'].iloc[-1]:.2f}")
            if "drs" in focus_df.columns:
                f2.metric("DRS open", f"{(focus_df['drs'] > 0).mean() * 100:.1f}%")
            if focus_ers:
                f3.metric("SOC empty time", f"{focus_ers.get('empty_pct', 0):.0f}% of lap")

    with tab_setup:
        st.caption(
            "Build from this practice starts from the garage you ran, diagnoses entry / mid / exit, "
            "then applies a small coordinated tweak. Δt estimates are directional (fuel is most trustworthy)."
        )
        setup = {}
        if session.get("setup_json"):
            try:
                setup = json.loads(session["setup_json"])
            except json.JSONDecodeError:
                setup = setup_snapshot(df, focus_lap)
        else:
            setup = setup_snapshot(df, focus_lap)

        baseline = normalize_setup(setup) if setup else {}
        sid = int(session["id"])
        state_key = f"setup_proposed_{sid}"
        if state_key not in st.session_state:
            st.session_state[state_key] = dict(baseline) if baseline else {}

        def _apply_setup_dict(values: dict) -> None:
            st.session_state[state_key] = dict(values)
            for param in SETUP_PARAMS:
                if param.key not in values:
                    continue
                st.session_state[f"setup_sl_{sid}_{param.key}"] = float(
                    display_value(param, values[param.key])
                )

        st.subheader("Setup builder")
        b1, b2, b3 = st.columns([1.2, 1, 1])
        with b1:
            track_options = list_tracks_with_setups()
            default_track = track if track in track_options else (track_options[0] if track_options else "Bahrain")
            setup_track = st.selectbox(
                "Track baseline",
                track_options,
                index=track_options.index(default_track) if default_track in track_options else 0,
                key=f"setup_track_{sid}",
            )
        with b2:
            setup_variant = st.radio("Variant", ["Quali", "Race"], horizontal=True, key=f"setup_var_{sid}")
        with b3:
            st.write("")
            st.write("")
            build_clicked = st.button("Build from this practice", type="primary", key=f"setup_build_{sid}")

        typical_pack = get_typical_setup(setup_track, setup_variant.lower())
        c_load1, c_load2, c_load3 = st.columns(3)
        if typical_pack and c_load1.button(
            f"Load typical {setup_track} {setup_variant}",
            key=f"load_typical_{sid}",
        ):
            _apply_setup_dict(typical_pack["setup"])
            st.session_state[f"setup_build_notes_{sid}"] = [
                typical_pack["notes"],
                f"Loaded typical {setup_track} {typical_pack['variant']} ({typical_pack['character']}).",
            ]
            st.rerun()
        if baseline and c_load2.button("Load session setup", key=f"load_session_{sid}"):
            _apply_setup_dict(baseline)
            st.session_state.pop(f"setup_build_notes_{sid}", None)
            st.rerun()
        if c_load3.button("Reset tweaker", key=f"setup_reset_{sid}"):
            if baseline:
                _apply_setup_dict(baseline)
            st.session_state.pop(f"setup_build_notes_{sid}", None)
            st.rerun()

        if typical_pack:
            st.caption(f"**{setup_track}** · {typical_pack['character']} — {typical_pack['notes']}")

        if build_clicked:
            built = build_setup_from_practice(
                df,
                setup,
                setup_track or track,
                variant=setup_variant.lower(),
                lap=focus_lap,
                prefer_typical_base=False,
            )
            _apply_setup_dict(built.setup)
            notes = list(built.findings)
            if built.diagnosis:
                notes.insert(0, f"Diagnosis: {built.diagnosis}.")
            if built.est_dt_vs_session is not None:
                notes.append(f"Est. vs your session setup: {built.est_dt_vs_session:+.3f}s")
            if built.est_dt_vs_typical is not None:
                notes.append(f"Est. vs track typical: {built.est_dt_vs_typical:+.3f}s")
            st.session_state[f"setup_build_notes_{sid}"] = notes
            st.session_state[f"setup_build_changes_{sid}"] = changes_frame(built).to_dict("records")
            st.rerun()

        if st.session_state.get(f"setup_build_notes_{sid}"):
            with st.expander("Builder findings", expanded=True):
                for note in st.session_state[f"setup_build_notes_{sid}"]:
                    st.markdown(f"- {note}")
                ch = st.session_state.get(f"setup_build_changes_{sid}") or []
                if ch:
                    st.dataframe(pd.DataFrame(ch), use_container_width=True, hide_index=True)

        if not baseline and not st.session_state.get(state_key):
            st.info("Load a typical track setup to start, or import a session that includes setup fields.")
        else:
            # Ensure proposed has keys even if session had no setup
            if not st.session_state.get(state_key) and typical_pack:
                st.session_state[state_key] = dict(typical_pack["setup"])
            compare_base = baseline if baseline else normalize_setup(
                (typical_pack or {}).get("setup") or st.session_state[state_key]
            )

            presets = setup_presets(compare_base) if compare_base else {}
            if presets:
                pcols = st.columns(min(4, max(1, len(presets))))
                for i, (name, preset) in enumerate(presets.items()):
                    if pcols[i % len(pcols)].button(name, key=f"preset_{sid}_{i}"):
                        _apply_setup_dict(preset)
                        st.rerun()

            proposed = dict(st.session_state[state_key])
            # Slider keys only for params present in proposed/compare_base
            active_keys = set(proposed) | set(compare_base)
            groups = {}
            for param in SETUP_PARAMS:
                if param.key not in active_keys:
                    continue
                groups.setdefault(param.group, []).append(param)

            left, right = st.columns([1.15, 1])
            with left:
                st.subheader("Garage tweaker")
                group_order = ("Fuel", "Aero", "Transmission", "Geometry", "Suspension", "Brakes", "Tyres")
                for group in group_order:
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
                            # Streamlit needs a clean step that divides the range
                            if step <= 0:
                                step = 1.0
                            slider_key = f"setup_sl_{sid}_{param.key}"
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
                st.session_state[state_key] = proposed

            est = estimate_setup_delta(
                compare_base,
                proposed,
                track=setup_track or track,
                reference_lap_time=float(focus_row["lap_time"]),
            )
            with right:
                st.subheader("Estimated impact")
                verb = "faster" if est.total_dt < 0 else "slower"
                base_label = "session setup" if baseline else "baseline"
                st.metric(
                    "Net estimated Δt",
                    f"{est.total_dt:+.3f} s",
                    f"{abs(est.total_dt):.3f}s {verb} than {base_label}",
                )
                st.caption(est.confidence)
                st.info(est.aero_balance_note)
                frame = estimate_to_frame(est)
                if not frame.empty:
                    st.plotly_chart(plots.setup_delta_bars(frame), use_container_width=True, key="chart_setup_delta")
                    st.plotly_chart(
                        plots.setup_breakdown_pie(est.breakdown),
                        use_container_width=True,
                        key="chart_setup_break",
                    )
                    show = frame.copy()
                    show["Est. Δt (s)"] = show["Est. Δt (s)"].map(lambda x: f"{x:+.3f}")
                    show["Δ units"] = show["Δ units"].map(lambda x: f"{x:+.3g}")
                    st.dataframe(show, use_container_width=True, hide_index=True)
                else:
                    st.write("Move a slider, load a typical setup, or build from practice.")

                # Quick card of current proposed key numbers
                st.subheader("Proposed card")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("FW / RW", f"{proposed.get('wing_setup_0', 0):.0f} / {proposed.get('wing_setup_1', 0):.0f}")
                m2.metric("Bias", f"{proposed.get('brake_bias_setup', 0) * 100:.0f}%")
                m3.metric("Fuel", f"{proposed.get('fuel_setup', 0):.0f}")
                m4.metric("ARB F/R", f"{proposed.get('arb_setup_0', 0):.0f}/{proposed.get('arb_setup_1', 0):.0f}")

        st.markdown("---")
        st.subheader("Tyre & fuel saving")
        stint_table = session_stint_table(df)
        s1, s2 = st.columns([1.2, 1])
        with s1:
            st.plotly_chart(
                plots.stint_efficiency_chart(stint_table),
                use_container_width=True,
                key="chart_stint_eff",
            )
            if not stint_table.empty:
                show = stint_table.copy()
                for col in ("lap_time", "fuel_used", "wear_delta_pct", "coast_pct", "tyre_temp_avg", "stint_score"):
                    if col in show.columns:
                        show[col] = show[col].map(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
                cols = [
                    c
                    for c in [
                        "lap",
                        "lap_time",
                        "fuel_used",
                        "wear_delta_pct",
                        "coast_pct",
                        "tyre_temp_avg",
                        "tyre_temp_spread",
                        "lockup_samples",
                        "stint_score",
                    ]
                    if c in show.columns
                ]
                st.dataframe(show[cols], use_container_width=True, hide_index=True)
        with s2:
            for tip in stint_saving_insights(df, focus_lap, reference_lap=ref_lap):
                css = {"tip": "insight-tip", "warning": "insight-warning", "info": "insight-info"}.get(
                    tip.severity, "insight-info"
                )
                st.markdown(
                    f'<div class="{css}"><strong>[{tip.category}] {tip.title}</strong><br/>{tip.detail}</div>',
                    unsafe_allow_html=True,
                )

    with tab_coach:
        lap_rows = get_session_laps(int(session["id"]), APP_ROOT)
        stored = None
        if not lap_rows.empty and ref_lap == best_lap:
            hit = lap_rows.loc[lap_rows["lap"] == focus_lap]
            if not hit.empty and hit.iloc[0].get("insights_json"):
                try:
                    stored = json.loads(hit.iloc[0]["insights_json"])
                except json.JSONDecodeError:
                    stored = None
        if stored:
            render_insights(stored)
        else:
            render_insights(
                generate_insights(df, focus_lap, reference_lap=ref_lap if ref_lap != focus_lap else best_lap)
            )
        if focus_lap != ref_lap and not corner_cmp.empty and "delta_s" in corner_cmp.columns:
            st.markdown("---")
            st.subheader("Corner callouts")
            worst = corner_cmp[corner_cmp["kind"] == "corner"].sort_values("delta_s", ascending=False).head(3)
            for _, row in worst.iterrows():
                if pd.notna(row.get("delta_s")) and row["delta_s"] > 0.02:
                    st.markdown(
                        f"- Losing **{row['delta_s']:.3f}s** in **{row['corner_name']}** "
                        f"({row['start_m']:.0f}–{row['end_m']:.0f} m)."
                    )

        st.markdown("---")
        st.subheader("ERS / 2026 energy callouts")
        for tip in practice_ers_insights(
            df, focus_lap, reference_lap=ref_lap, track=track, track_length=track_length
        ):
            if tip.severity in ("tip", "warning"):
                css = "insight-tip" if tip.severity == "tip" else "insight-warning"
                st.markdown(
                    f'<div class="{css}"><strong>{tip.title}</strong><br/>{tip.detail}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")
        st.subheader("Tyre / fuel saving callouts")
        for tip in stint_saving_insights(df, focus_lap, reference_lap=ref_lap):
            if tip.severity in ("tip", "warning"):
                css = "insight-tip" if tip.severity == "tip" else "insight-warning"
                st.markdown(
                    f'<div class="{css}"><strong>[{tip.category}] {tip.title}</strong><br/>{tip.detail}</div>',
                    unsafe_allow_html=True,
                )


def main() -> None:
    init_db(APP_ROOT)
    ensure_progress_schema(APP_ROOT)

    st.title("🏎️ F1 26 Telemetry Analyzer")
    st.caption("Session library · track dossier · corner losses · map cursor")

    if "progress_backfilled" not in st.session_state:
        with st.spinner("Indexing progress from existing sessions…"):
            n = backfill_progress_from_library(APP_ROOT)
            st.session_state["progress_backfilled"] = n

    stats = library_stats(APP_ROOT)
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Sessions", stats["sessions"])
    s2.metric("Tracks", stats["tracks"])
    s3.metric("Library size", format_bytes(stats["stored_bytes"]))
    s4.metric("CSV space saved", format_bytes(max(0, stats["saved_bytes"])))

    with st.sidebar:
        st.header("Library")
        mode = st.radio(
            "Mode",
            ["Browse sessions", "Track dossier", "Import CSV"],
            index=0,
        )
        if mode == "Import CSV":
            sidebar_import()
            st.stop()
        if mode == "Track dossier":
            pass  # rendered below
        else:
            session = pick_session()
            if session is None:
                st.stop()
            st.markdown(
                f"**{session.get('car') or 'Car'}** · **{session.get('track') or 'Track'}**  \n"
                f"Source: `{session.get('source_name')}`"
            )
            if st.button("Delete session from library", type="secondary"):
                delete_session(int(session["id"]), APP_ROOT)
                st.session_state.pop("selected_session_id", None)
                st.cache_data.clear()
                st.rerun()

    if mode == "Track dossier":
        render_dossier()
        return

    with st.spinner("Loading compact telemetry…"):
        df = cached_session_df(
            int(session["id"]),
            session["telemetry_path"],
            int(session.get("stored_size_bytes") or 0),
        )

    summary = build_lap_summary(df)
    if summary.empty:
        st.error("Session has no valid laps.")
        st.stop()

    outline = get_track_outline(session["track"], APP_ROOT) if session.get("track") else None
    render_analysis(session, df, summary, outline)


if __name__ == "__main__":
    main()
