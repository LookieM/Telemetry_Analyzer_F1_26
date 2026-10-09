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
    ANALYSIS_COLUMNS,
    SESSION_TYPES,
    delete_session,
    ensure_session_meta_schema,
    get_session,
    get_session_laps,
    get_track_outline,
    init_db,
    library_stats,
    list_sessions,
    list_tracks,
    load_session_telemetry,
    update_session_tags,
)
from telemetry.ers import (
    channels_2026_insights,
    ers_by_corner,
    ers_by_distance,
    lap_ers_summary,
    practice_ers_insights,
    recommended_deploy_map,
    session_ers_table,
)
from telemetry.conditions import (
    STATE_LABELS,
    STATE_OPTIONS,
    _as_state,
    compose_conditions,
    label_to_state,
    parse_track_state,
    split_conditions,
    weather_banner,
)
from telemetry.track_catalog import TRACK_LENGTHS_M
from telemetry.import_session import import_csv
from telemetry.corner_engineer import render_corner_engineer_panel
from telemetry.insights import Insight, compare_brake_markers, generate_insights
from telemetry.loader import list_local_csvs, resolve_session_setup
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
    scrub_improbable_lap_records,
    set_track_goal,
    track_dossier,
)
from telemetry.garage_ui import (
    apply_setup_to_state,
    render_garage_tweaker,
)
from telemetry.race_windows import stint_window_insights
from telemetry.session_compare import (
    compare_sessions,
    pb_reference_session,
    session_label,
)
from telemetry.setup_builder import build_setup_from_practice, changes_frame
from telemetry.coach import CoachItem, coach_feed_for_session, setup_followup_items, setup_summary_item
from telemetry.diagnosis import build_session_diagnosis
from telemetry.setup_history import backfill_setup_fingerprints, setup_timeline
from telemetry.setup_eval import NOISE_FLOOR, clear_run_cache, load_session_runs
from telemetry.setup_journal_ui import (
    experiments_frame,
    render_compare_panel,
    render_followup_cards,
    render_runs_panel,
)
from telemetry.setup_log import evaluate_all, followup_entries, load_history, save_recommendation
from telemetry.runs import best_run
from telemetry.lap_views import driver_trace
from telemetry.ui.track_map import lap_map
from telemetry.compounds import get_allocation
from telemetry.strategy_ui import render_strategy
from telemetry.session_tags import backfill_session_tags
from telemetry.tyres import clear_cache as clear_tyre_cache
from telemetry.tyres_ui import render_tyres_tab
from telemetry.setup_tweaker import normalize_setup
from telemetry.ers_2026_ui import render_2026_channels_panel, render_stint_windows_panel
from telemetry.stint_coach import session_stint_table, stint_saving_insights
from telemetry.track_setups import get_typical_setup, list_tracks_with_setups


def _open_garage_for_track(track: str) -> None:
    """Button callback: navigate to Garage on the canonical track name."""
    canon = normalize_track_name(track) or track
    st.session_state["nav_mode"] = "Garage"
    st.session_state["garage_track"] = canon
    st.session_state["garage_track_select"] = canon
    st.session_state["garage_variant"] = "Quali"
    st.session_state["garage_nav_pending"] = True


st.set_page_config(
    page_title="TELEMETRIA · F1 26",
    page_icon="T",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

    :root {
        --ink: #1A1A1A;
        --muted: #5C5C5C;
        --paper: #F4F2EF;
        --sidebar: #EBE8E3;
        --rule: #D4D0C8;
        --accent: #C8102E;
        --font-sans: "IBM Plex Sans", "Segoe UI", sans-serif;
        --font-mono: "IBM Plex Mono", ui-monospace, monospace;
    }

    html, body, [class*="css"] {
        font-family: var(--font-sans);
        color: var(--ink);
    }

    .stApp {
        background: var(--paper);
    }

    [data-testid="stSidebar"] {
        background: var(--sidebar);
        border-right: 1px solid var(--rule);
    }

    [data-testid="stSidebar"] * {
        font-family: var(--font-sans);
    }

    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 2.5rem;
        max-width: 1400px;
    }

    h1, h2, h3 {
        font-family: var(--font-sans) !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em;
        color: var(--ink) !important;
    }

    .brand-mark {
        font-family: var(--font-sans);
        font-weight: 700;
        font-size: 1.65rem;
        letter-spacing: 0.14em;
        color: var(--ink);
        margin: 0 0 0.15rem 0;
        line-height: 1.1;
    }

    .brand-sub {
        font-family: var(--font-mono);
        font-size: 0.78rem;
        color: var(--muted);
        letter-spacing: 0.04em;
        margin: 0 0 1rem 0;
    }

    div[data-testid="stMetricValue"] {
        font-family: var(--font-mono) !important;
        font-size: 1.15rem !important;
        font-weight: 500 !important;
        color: var(--ink) !important;
    }

    div[data-testid="stMetricLabel"] {
        font-family: var(--font-sans) !important;
        color: var(--muted) !important;
        font-size: 0.8rem !important;
    }

    .insight-tip, .insight-warning, .insight-info {
        border-left: 2px solid #1A1A1A;
        padding: 0.55rem 0.85rem;
        margin: 0.45rem 0;
        background: transparent;
        border-top: none;
        border-right: none;
        border-bottom: 1px solid var(--rule);
        font-size: 0.92rem;
        line-height: 1.45;
        color: var(--ink);
    }

    .insight-warning {
        border-left-color: var(--accent);
    }

    .insight-tip strong, .insight-warning strong, .insight-info strong {
        font-weight: 600;
        letter-spacing: -0.01em;
    }

    /* Primary actions → signal red */
    div[data-testid="stButton"] > button[kind="primary"],
    button[data-testid="baseButton-primary"] {
        background-color: var(--accent) !important;
        border-color: var(--accent) !important;
        color: #fff !important;
        font-family: var(--font-sans) !important;
        font-weight: 500 !important;
        border-radius: 2px !important;
    }

    div[data-testid="stButton"] > button[kind="secondary"],
    button[data-testid="baseButton-secondary"] {
        border-radius: 2px !important;
        border-color: #B8B3AA !important;
        font-family: var(--font-sans) !important;
    }

    /* Tabs / radios: quieter */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.25rem;
        border-bottom: 1px solid var(--rule);
    }

    .stTabs [data-baseweb="tab"] {
        font-family: var(--font-sans);
        font-weight: 500;
    }

    hr {
        border-color: var(--rule) !important;
        margin: 1.2rem 0 !important;
    }

    /* Dataframes: less glossy */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--rule);
        border-radius: 2px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

APP_ROOT = Path(__file__).resolve().parent


# cache_resource hands back the same frame every rerun (no pickle copy of ~160k rows), which also
# lets the per-frame summary / lap caches in telemetry.metrics hit across reruns. Nothing mutates it.
@st.cache_resource(show_spinner=False, max_entries=3)
def cached_session_df(session_id: int, telemetry_path: str, stored_size: int) -> pd.DataFrame:
    return load_session_telemetry(session_id, APP_ROOT, columns=ANALYSIS_COLUMNS)


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


def render_coach_feed(headline: str, top: list[CoachItem], rest: list[CoachItem]) -> None:
    """Ranked session engineer feed with headline + domain expanders."""
    st.markdown(f"**Session read:** {headline}")
    if not top and not rest:
        st.info("No session callouts yet — need more probable laps or richer telemetry channels.")
        return

    kind_css = {
        "drive": "insight-tip",
        "setup": "insight-warning",
        "manage": "insight-info",
        "observe": "insight-info",
    }

    st.subheader("Top callouts")
    for item in top:
        css = kind_css.get(item.action_kind, "insight-info")
        badge = item.action_kind.upper()
        st.markdown(
            f'<div class="{css}">'
            f'<span style="opacity:0.7;font-size:0.75rem;">{badge} · {item.domain}</span><br/>'
            f"<strong>{item.title}</strong><br/>{item.detail}</div>",
            unsafe_allow_html=True,
        )

    if rest:
        by_domain: dict[str, list[CoachItem]] = {}
        for item in rest:
            by_domain.setdefault(item.domain, []).append(item)
        with st.expander(f"More callouts ({len(rest)})", expanded=False):
            for domain, items in sorted(by_domain.items()):
                st.markdown(f"**{domain.title()}**")
                for item in items:
                    css = kind_css.get(item.action_kind, "insight-info")
                    st.markdown(
                        f'<div class="{css}"><strong>{item.title}</strong><br/>{item.detail}</div>',
                        unsafe_allow_html=True,
                    )


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


CURSOR_KEY = "cursor_distance"


def pin_cursor(distance: float | None) -> None:
    """
    Pin the lap cursor from a map / chart click.

    The cursor slider owns CURSOR_KEY, which cannot be written once the slider exists in this
    run — so the value waits under a pending key and is applied before the slider next run.
    """
    if distance is None:
        return
    if abs(float(distance) - float(st.session_state.get(CURSOR_KEY, 0.0))) > 0.75:
        st.session_state[f"{CURSOR_KEY}_pending"] = float(distance)
        st.rerun()


def sidebar_import() -> None:
    st.subheader("Import SRT CSV")
    local = list_local_csvs(APP_ROOT)
    src = st.radio("Source", ["Project folder", "Upload", "Custom path"], horizontal=True, key="import_src")
    path: Path | None = None
    upload_name: str | None = None  # uploads go through a temp file; keep the real name

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
            upload_name = up.name
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
    type_opts = ["(untagged)"] + list(SESSION_TYPES)
    session_type = st.selectbox("Session type", type_opts, index=0, key="import_session_type")
    wx_col, note_col = st.columns([1, 1.4])
    with wx_col:
        import_wx = st.selectbox("Track state", STATE_OPTIONS, index=0, key="import_track_state")
    with note_col:
        conditions_notes = st.text_input(
            "Conditions notes",
            placeholder="Rubber, fuel load, standing water…",
            key="import_conditions_notes",
        )
    conditions = compose_conditions(label_to_state(import_wx), conditions_notes)
    notes = st.text_input("Session notes (optional)", placeholder="Bahrain race — softs…")

    if st.button("Import into library", type="primary", disabled=path is None):
        assert path is not None
        tag = "" if session_type == "(untagged)" else session_type
        with st.spinner("Importing & compressing…"):
            try:
                result = import_csv(
                    path,
                    app_root=APP_ROOT,
                    delete_source=delete_src,
                    notes=notes,
                    session_type=tag,
                    conditions=conditions,
                    source_name=upload_name,
                )
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
    type_opts = ["All types"] + list(SESSION_TYPES) + ["(untagged)"]
    type_filter = st.selectbox("Filter session type", type_opts, key="browse_type_filter")

    view = sessions if track_filter == "All tracks" else sessions[sessions["track"] == track_filter]
    if type_filter == "(untagged)":
        view = view[view["session_type"].fillna("").astype(str).str.strip() == ""]
    elif type_filter != "All types":
        view = view[view["session_type"] == type_filter]

    if view.empty:
        st.info("No sessions match these filters.")
        return None

    labels = []
    ids = []
    for _, row in view.iterrows():
        best = format_lap_time(float(row["best_lap_time"])) if pd.notna(row["best_lap_time"]) else "—"
        tag = row.get("session_type") or ""
        tag_bit = f"{tag} · " if tag else ""
        labels.append(
            f"#{row['id']} · {tag_bit}{row.get('track') or '?'} · {row.get('car') or '?'} · "
            f"{int(row['lap_count'])} laps · best {best} · {format_bytes(row.get('stored_size_bytes'))}"
        )
        ids.append(int(row["id"]))

    default_id = st.session_state.get("selected_session_id")
    index = ids.index(default_id) if default_id in ids else 0
    choice = st.selectbox("Session", range(len(ids)), format_func=lambda i: labels[i], index=index)
    session_id = ids[choice]
    st.session_state["selected_session_id"] = session_id
    return get_session(session_id, APP_ROOT)


def render_cross_session_compare(
    focus_session_id: int,
    *,
    track: str | None = None,
    key_prefix: str = "xsess",
) -> None:
    """Focus session vs reference session overlay (default ref = PB for track)."""
    focus = get_session(focus_session_id, APP_ROOT)
    if not focus:
        st.warning("Focus session missing.")
        return

    track_name = normalize_track_name(track or focus.get("track")) or focus.get("track")
    same_track = list_sessions(APP_ROOT, track=track_name) if track_name else list_sessions(APP_ROOT)
    if same_track.empty or len(same_track) < 2:
        st.info("Need at least two sessions on this track for a cross-session overlay.")
        return

    pb = pb_reference_session(track_name, APP_ROOT) if track_name else None
    ref_ids = [int(r) for r in same_track["id"].tolist() if int(r) != focus_session_id]
    if not ref_ids:
        st.info("No other session available as reference.")
        return

    default_ref = int(pb["id"]) if pb and int(pb["id"]) in ref_ids else ref_ids[0]
    # Prefer PB even if it's the focus — then pick next-best other session
    if pb and int(pb["id"]) == focus_session_id:
        default_ref = ref_ids[0]

    labels = {int(r["id"]): session_label(dict(r)) for _, r in same_track.iterrows()}
    ref_index = ref_ids.index(default_ref) if default_ref in ref_ids else 0
    ref_id = st.selectbox(
        "Reference session",
        ref_ids,
        index=ref_index,
        format_func=lambda i: labels.get(i, f"#{i}")
        + (" ★ PB" if pb and int(pb["id"]) == i else ""),
        key=f"{key_prefix}_ref",
    )
    if pb and int(pb["id"]) == int(ref_id):
        st.caption("Reference defaults to your personal-best session for this track.")

    try:
        result = compare_sessions(focus_session_id, int(ref_id), app_root=APP_ROOT)
    except Exception as exc:
        st.error(f"Compare failed: {exc}")
        return

    gap = result.focus_time - result.ref_time
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Focus", f"#{result.focus_session['id']} L{result.focus_lap}", format_lap_time(result.focus_time))
    m2.metric(
        "Reference",
        f"#{result.ref_session['id']} L{result.ref_lap}" + (" ★" if result.ref_is_pb else ""),
        format_lap_time(result.ref_time),
    )
    m3.metric("Lap Δ", f"{gap:+.3f}s", help="Positive = focus slower than reference")
    final_d = float(result.aligned["delta_time"].iloc[-1]) if not result.aligned.empty else gap
    m4.metric("Integrated Δt", f"{final_d:+.3f}s")

    corners = resolve_corners(result.track, result.track_length)
    if not result.aligned.empty:
        st.plotly_chart(
            plots.telemetry_overlay(
                result.aligned,
                f"S{result.ref_session['id']} L{result.ref_lap}",
                f"S{result.focus_session['id']} L{result.focus_lap}",
                corners=corners,
            ),
            use_container_width=True,
            key=f"{key_prefix}_overlay",
        )
    if not result.corner_cmp.empty:
        st.subheader("Corner times")
        st.plotly_chart(
            plots.corner_delta_bars(result.corner_cmp),
            use_container_width=True,
            key=f"{key_prefix}_corners",
        )
        if "delta_s" in result.corner_cmp.columns:
            render_corner_engineer_panel(
                result.corner_cmp,
                title="Engineer — phases vs reference session",
                top_n=3,
            )
        else:
            table = result.corner_cmp.copy()
            for col in ("time_s", "ref_time_s", "delta_s", "vmin", "ref_vmin"):
                if col in table.columns:
                    table[col] = table[col].map(lambda x: f"{x:.3f}" if pd.notna(x) else "—")
            st.dataframe(table, use_container_width=True, hide_index=True)


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

    setups = list_tracks_with_setups()
    canon = normalize_track_name(track)
    has_setup = bool(canon and canon in setups)

    if not in_library:
        st.info(f"Import an SRT session from **{track}** to unlock PB history, consistency, and the race map outline.")
        if has_setup:
            st.button(
                f"Open Garage for {track}",
                type="primary",
                key="dossier_open_garage",
                on_click=_open_garage_for_track,
                args=(track,),
            )
        return

    # Raced track: still offer Garage jump
    if has_setup:
        st.button(
            f"Open Garage for {track}",
            key="dossier_open_garage_raced",
            on_click=_open_garage_for_track,
            args=(track,),
        )

    type_opts = ["All types"] + list(SESSION_TYPES)
    type_filter = st.selectbox("Filter by session type", type_opts, key="dossier_type_filter")
    type_arg = None if type_filter == "All types" else type_filter

    dossier = track_dossier(track, APP_ROOT, session_type=type_arg)
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
        if goal:
            default_goal = float(goal["target_lap_time"])
        elif dossier.get("best_time"):
            default_goal = float(dossier["best_time"]) - 0.5
        else:
            default_goal = 90.0
        # Adaptive floor so a bad stored goal / PB cannot crash Streamlit
        min_goal = 40.0
        if default_goal < min_goal:
            min_goal = max(20.0, float(default_goal) - 1.0)
        default_goal = float(min(max(default_goal, min_goal), 200.0))
        target = st.number_input(
            "Goal lap time (seconds)",
            min_value=float(min_goal),
            max_value=200.0,
            value=default_goal,
            step=0.1,
        )
        goal_notes = st.text_input("Goal notes", value=(goal or {}).get("notes") or "")
        if st.button("Save goal"):
            set_track_goal(track, target, goal_notes, APP_ROOT)
            st.success("Goal saved.")
            st.rerun()
    with g2:
        if goal and dossier.get("best_time"):
            gap = float(dossier["best_time"]) - float(goal["target_lap_time"])
            st.metric("Gap to goal", f"{gap:+.3f}s", help="Negative means you already beat the goal.")
        st.caption("Goals are stored in the local DB and survive CSV deletion. Sub-45s times are ignored as takebacks.")

    left, right = st.columns(2)
    with left:
        st.plotly_chart(plots.pb_history_chart(dossier["pb_history"]), use_container_width=True, key="dossier_pb")
    with right:
        st.plotly_chart(plots.session_bests_chart(dossier["sessions"]), use_container_width=True, key="dossier_sessions")

    st.subheader("Visit history")
    sess = dossier["sessions"].copy()
    if not sess.empty:
        cols = [
            c
            for c in [
                "id",
                "created_at",
                "session_type",
                "conditions",
                "car",
                "lap_count",
                "best_lap_time",
                "setup_fingerprint",
                "source_name",
                "notes",
            ]
            if c in sess.columns
        ]
        show = sess[cols].copy()
        show["best_lap_time"] = show["best_lap_time"].map(format_lap_time)
        st.dataframe(show, use_container_width=True, hide_index=True)

    st.subheader("Setup evolution")
    timeline = dossier.get("setup_timeline")
    if isinstance(timeline, pd.DataFrame) and not timeline.empty:
        tl = timeline.sort_values("created_at", ascending=False).copy()
        display = tl[
            [
                c
                for c in [
                    "session_id",
                    "created_at",
                    "session_type",
                    "best_lap",
                    "best_lap_time",
                    "pace_delta_s",
                    "setup_delta_summary",
                    "setup_fingerprint",
                    "conditions",
                ]
                if c in tl.columns
            ]
        ].copy()
        if "best_lap_time" in display.columns:
            display["best_lap_time"] = display["best_lap_time"].map(format_lap_time)
        if "pace_delta_s" in display.columns:
            display["pace_delta_s"] = display["pace_delta_s"].map(
                lambda x: f"{x:+.3f}s" if pd.notna(x) else "—"
            )
        st.caption(
            "Each row is a session best linked to its setup fingerprint. "
            "Setup Δ is vs the previous visit; pace Δ is best-lap response."
        )
        st.dataframe(display, use_container_width=True, hide_index=True)
        changed = tl[tl["setup_changed"] == True] if "setup_changed" in tl.columns else pd.DataFrame()
        if not changed.empty:
            latest_change = changed.iloc[0]
            pace = latest_change.get("pace_delta_s")
            pace_txt = f"{pace:+.3f}s" if pd.notna(pace) else "n/a"
            st.markdown(
                f"Latest setup change (session **#{int(latest_change['session_id'])}**): "
                f"{latest_change.get('setup_delta_summary')} → pace {pace_txt}"
            )
    else:
        st.caption("Setup timeline appears after imports with setup channels.")

    st.subheader("Cross-session overlay")
    if not sess.empty and len(sess) >= 2:
        focus_ids = [int(i) for i in sess["id"].tolist()]
        focus_id = st.selectbox(
            "Focus session",
            focus_ids,
            index=0,
            format_func=lambda i: session_label(get_session(i, APP_ROOT) or {"id": i}),
            key="dossier_xsess_focus",
        )
        render_cross_session_compare(int(focus_id), track=track, key_prefix="dossier_xsess")
    elif not sess.empty:
        st.caption("Import a second session on this track to overlay vs PB / another run.")
    else:
        st.caption("No sessions for this filter.")

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
    sid = int(session["id"])
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
            key=f"focus_lap_{sid}",
        )
        ref_lap = st.selectbox(
            "Reference lap",
            laps,
            index=laps.index(best_lap),
            format_func=lambda L: f"Lap {L} — {format_lap_time(float(summary.loc[summary.lap == L, 'lap_time'].iloc[0]))}",
            key=f"ref_lap_{sid}",
        )
        prev_focus_key = f"coach_focus_lap_{sid}"
        if prev_focus_key in st.session_state and st.session_state[prev_focus_key] != focus_lap:
            st.session_state.pop(f"setup_coach_item_{sid}", None)
        st.session_state[prev_focus_key] = focus_lap
        map_color = st.selectbox("Map colour", ["speed", "throttle", "brake", "delta"], index=0)

        st.markdown("---")
        st.subheader("Lap cursor")
        st.caption("Hover the map or any trace for live channels · click to pin · scrub distance below.")
        max_dist = float(track_length or 5408)
        pending = st.session_state.pop(f"{CURSOR_KEY}_pending", None)
        if pending is not None:
            st.session_state[CURSOR_KEY] = min(max_dist, max(0.0, float(pending)))
        # Clamp: a cursor from a longer track would break the slider after switching sessions.
        st.session_state[CURSOR_KEY] = min(max_dist, max(0.0, float(st.session_state.get(CURSOR_KEY, 0.0))))
        st.slider("Distance (m)", 0.0, max_dist, step=1.0, key=CURSOR_KEY)

    cursor = float(st.session_state.get(CURSOR_KEY, 0.0))
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
            "vs Session",
            "Single lap",
            "Tyres",
            "Strategy",
            "ERS / 2026",
            "Setup / Stint",
            "Coach",
        ]
    )
    (
        tab_overview,
        tab_map,
        tab_corners,
        tab_compare,
        tab_xsess,
        tab_single,
        tab_tyres,
        tab_strategy,
        tab_ers,
        tab_setup,
        tab_coach,
    ) = tabs

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
            st.subheader("Tags")
            type_opts = ["(untagged)"] + list(SESSION_TYPES)
            cur_type = session.get("session_type") or ""
            type_idx = type_opts.index(cur_type) if cur_type in type_opts else 0
            edit_type = st.selectbox("Session type", type_opts, index=type_idx, key=f"sess_type_{session['id']}")
            cur_state, cur_wx_notes = split_conditions(session.get("conditions") or "")
            wx_i = STATE_OPTIONS.index(STATE_LABELS[cur_state])
            edit_wx = st.selectbox(
                "Track state",
                STATE_OPTIONS,
                index=wx_i,
                key=f"sess_wx_{session['id']}",
            )
            edit_cond_notes = st.text_input(
                "Conditions notes",
                value=cur_wx_notes,
                key=f"sess_cond_{session['id']}",
            )
            edit_cond = compose_conditions(label_to_state(edit_wx), edit_cond_notes)
            notes = st.text_area("Notes", value=session.get("notes") or "", height=100)
            if st.button("Save tags & notes", key=f"save_tags_{session['id']}"):
                update_session_tags(
                    int(session["id"]),
                    session_type="" if edit_type == "(untagged)" else edit_type,
                    conditions=edit_cond,
                    notes=notes,
                    app_root=APP_ROOT,
                )
                st.success("Saved.")
                st.cache_data.clear()
                st.rerun()
            if session.get("setup_fingerprint"):
                st.caption(f"Setup fingerprint: `{session['setup_fingerprint']}`")
            banner = weather_banner(cur_state)
            if banner:
                st.info(banner)
            show = summary.copy()
            show["lap_time"] = show["lap_time"].map(lambda x: f"{x:.3f}")
            show["delta_best"] = show["delta_best"].map(lambda x: f"{x:+.3f}")
            if "compound" in show.columns:
                alloc = get_allocation(track, APP_ROOT)
                show["compound"] = show["compound"].map(alloc.label)
            cols = [c for c in ["lap", "lap_class", "lap_time", "delta_best", "vmax", "throttle_full_pct", "coast_pct", "fuel_used", "tyre_wear_avg", "compound", "lockup_samples"] if c in show.columns]
            st.dataframe(show[cols], use_container_width=True, hide_index=True)

    ref_for_view = ref_df if focus_lap != ref_lap else None
    lap_labels = {"cmp_label": f"L{focus_lap}", "ref_label": f"L{ref_lap}"}

    with tab_map:
        m1, m2 = st.columns([1.15, 1])
        with m1:
            pin_cursor(
                lap_map(
                    focus_df,
                    key=f"map_race_{sid}",
                    ref_df=ref_for_view,
                    color=map_color,
                    outline=outline,
                    corners=corners,
                    pinned_d=cursor,
                    title=f"{track or 'Track'} — lap {focus_lap}"
                    + (f" vs lap {ref_lap}" if ref_for_view is not None else ""),
                    height=600,
                    **lap_labels,
                )
            )
            if corner_here:
                st.caption(f"Pinned: {corner_here.name} · {corner_here.start:.0f}–{corner_here.end:.0f} m")
        with m2:
            pin_cursor(
                driver_trace(
                    focus_df,
                    key=f"trace_race_{sid}",
                    ref_df=ref_for_view,
                    corners=corners,
                    cursor=cursor,
                    pane_height=105,
                    **lap_labels,
                )
            )
            st.caption("Drag on a trace to zoom every pane · double-click to reset.")

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
            if focus_lap != ref_lap and not corner_cmp.empty and "delta_s" in corner_cmp.columns:
                # [P1 engineer] phase metrics + sentences — see telemetry.corner_engineer
                render_corner_engineer_panel(corner_cmp, title="Engineer — corner phases", top_n=3)
                if not aligned.empty and all(
                    c in aligned.columns for c in ("ref_brake", "cmp_brake", "ref_speed", "cmp_speed", "lap_distance")
                ):
                    markers = compare_brake_markers(aligned)
                    flagged = [m for m in markers if m.get("flagged")]
                    if flagged:
                        st.subheader("Brake markers vs reference")
                        for m in sorted(flagged, key=lambda x: abs(x["delta_m"]), reverse=True)[:5]:
                            when = "later" if m["delta_m"] > 0 else "earlier"
                            st.markdown(
                                f"- **{m['cmp_onset_m']:.0f} m**: {abs(m['delta_m']):.0f} m {when} than ref "
                                f"(ref {m['ref_onset_m']:.0f} m · approach ~{m['approach_speed']:.0f} km/h)"
                            )
            else:
                table = focus_corners.copy()
                for col in ("time_s", "vmin", "brake_point_m", "turn_in_speed", "exit_speed", "throttle_on_m", "trail_brake_s"):
                    if col in table.columns:
                        table[col] = table[col].map(lambda x: f"{x:.3f}" if pd.notna(x) else "—")
                st.dataframe(table, use_container_width=True, hide_index=True)

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
                pin_cursor(
                    lap_map(
                        focus_df,
                        key=f"map_cmp_{sid}",
                        ref_df=ref_df,
                        color=map_color,
                        outline=outline,
                        corners=corners,
                        pinned_d=cursor,
                        title=f"Lap {focus_lap} vs lap {ref_lap} — colour: {map_color}",
                        height=480,
                        **lap_labels,
                    )
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
            pin_cursor(
                driver_trace(
                    focus_df,
                    key=f"trace_cmp_{sid}",
                    ref_df=ref_df,
                    corners=corners,
                    cursor=cursor,
                    **lap_labels,
                )
            )

    with tab_xsess:
        st.caption(
            "Overlay this session’s best lap against another library session "
            "(defaults to the personal-best session for this track)."
        )
        render_cross_session_compare(int(session["id"]), track=track, key_prefix=f"browse_xsess_{session['id']}")

    with tab_single:
        col_a, col_b = st.columns([1.1, 1.4])
        with col_a:
            pin_cursor(
                lap_map(
                    focus_df,
                    key=f"map_single_{sid}",
                    color=map_color,
                    outline=outline,
                    corners=corners,
                    pinned_d=cursor,
                    title=f"Lap {focus_lap}",
                    height=460,
                    cmp_label=f"L{focus_lap}",
                )
            )
            st.plotly_chart(plots.gg_diagram(focus_df), use_container_width=True, key="chart_single_gg")
        with col_b:
            pin_cursor(
                driver_trace(focus_df, key=f"trace_single_{sid}", corners=corners, cursor=cursor, cmp_label=f"L{focus_lap}")
            )
            st.caption("Hover the map or a trace for live channels · click to pin · drag to zoom, double-click to reset.")

    with tab_tyres:
        pin_cursor(
            render_tyres_tab(
                session,
                df,
                summary,
                focus_lap=focus_lap,
                focus_df=focus_df,
                corners=corners,
                cursor=cursor,
                app_root=APP_ROOT,
            )
        )

    with tab_strategy:
        if track:
            render_strategy(
                track,
                _as_state(session.get("conditions")),
                APP_ROOT,
                key=f"strat_{sid}",
                session=session,
                summary=summary,
                df=df,
            )
        else:
            st.info("Track unknown for this session — use the Strategy planner in the sidebar.")

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

        st.markdown("---")
        render_2026_channels_panel(df, focus_lap, reference_lap=ref_lap, chart_prefix=f"ers_{session['id']}")

    with tab_setup:
        st.caption(
            "Engineer mode: build from this practice starts from the garage you ran, diagnoses entry / mid / exit, "
            "then applies a small coordinated tweak. "
            "Browse any track without a session via sidebar **Garage**."
        )
        render_followup_cards(session, APP_ROOT)
        with st.expander("Runs in this session", expanded=False):
            render_runs_panel(session, APP_ROOT)
        with st.expander("Compare with an earlier session (A/B)", expanded=False):
            if not track:
                st.caption("Track unknown for this session.")
            elif st.toggle("Load comparison", key=f"cmp_load_{sid}"):
                render_compare_panel(session, track, APP_ROOT, key=f"cmp_{sid}")
        if track:
            with st.expander("Setup evolution on this track", expanded=False):
                tl = setup_timeline(track, APP_ROOT)
                if tl.empty:
                    st.caption("No setup history yet.")
                else:
                    show_tl = tl.sort_values("created_at", ascending=False).head(12)
                    disp = show_tl[
                        [
                            c
                            for c in [
                                "session_id",
                                "created_at",
                                "best_lap_time",
                                "pace_delta_s",
                                "setup_delta_summary",
                                "setup_fingerprint",
                            ]
                            if c in show_tl.columns
                        ]
                    ].copy()
                    if "best_lap_time" in disp.columns:
                        disp["best_lap_time"] = disp["best_lap_time"].map(format_lap_time)
                    if "pace_delta_s" in disp.columns:
                        disp["pace_delta_s"] = disp["pace_delta_s"].map(
                            lambda x: f"{x:+.3f}s" if pd.notna(x) else "—"
                        )
                    st.dataframe(disp, use_container_width=True, hide_index=True)
                    st.caption("Best lap from each session is linked to that run’s setup fingerprint.")
                    exp_df = experiments_frame(track, APP_ROOT)
                    if not exp_df.empty:
                        st.markdown("**Measured experiments** (fuel-corrected, same track state)")
                        st.dataframe(exp_df, use_container_width=True, hide_index=True)

        ui_id = f"sess_{sid}"
        state_key = f"setup_proposed_{sid}_{focus_lap}"

        st.subheader("Setup builder")
        st.caption("Garage suggestions use the **session read** (all probable laps vs PB); focus lap selects which garage snapshot to start from.")
        sess_wx = parse_track_state(session.get("conditions"))
        b1, b2, b3, b4 = st.columns([1.2, 0.9, 1, 1])
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
            setup_wx = st.selectbox(
                "Track state",
                STATE_OPTIONS,
                index=STATE_OPTIONS.index(STATE_LABELS[sess_wx]),
                key=f"setup_wx_{sid}",
            )
            setup_conditions = compose_conditions(label_to_state(setup_wx))
        with b4:
            st.write("")
            st.write("")
            build_clicked = st.button("Build from this practice", type="primary", key=f"setup_build_{sid}")

        setup_base = st.radio(
            "Start from",
            ["Session garage", "Best verified", "Track typical"],
            horizontal=True,
            key=f"setup_base_{sid}",
            help="Best verified = the fastest run on this track (enough laps, same track state, fuel-corrected). "
            "Builder also learns from earlier experiments: it backs out moves that cost time and skips levers that hurt.",
        )

        typical_pack = get_typical_setup(setup_track, setup_variant.lower(), conditions=setup_conditions)

        stored_setup = {}
        if session.get("setup_json"):
            try:
                stored_setup = json.loads(session["setup_json"])
            except json.JSONDecodeError:
                stored_setup = {}

        setup, setup_source = resolve_session_setup(
            stored_setup,
            df,
            focus_lap,
            typical_setup=(typical_pack or {}).get("setup"),
        )
        baseline = setup if setup else {}
        if state_key not in st.session_state:
            st.session_state[state_key] = dict(baseline) if baseline else {}
        c_load1, c_load2, c_load3 = st.columns(3)
        if typical_pack and c_load1.button(
            f"Load typical {setup_track} {setup_variant}",
            key=f"load_typical_{sid}",
        ):
            apply_setup_to_state(state_key, ui_id, typical_pack["setup"])
            st.session_state[f"setup_build_notes_{sid}"] = [
                typical_pack["notes"],
                f"Loaded typical {setup_track} {typical_pack['variant']} ({typical_pack['character']}).",
            ]
            st.rerun()
        if baseline and c_load2.button("Load session setup", key=f"load_session_{sid}"):
            apply_setup_to_state(state_key, ui_id, baseline)
            st.session_state.pop(f"setup_build_notes_{sid}", None)
            st.rerun()
        if c_load3.button("Reset tweaker", key=f"setup_reset_{sid}"):
            if baseline:
                apply_setup_to_state(state_key, ui_id, baseline)
            elif typical_pack:
                apply_setup_to_state(state_key, ui_id, typical_pack["setup"])
            st.session_state.pop(f"setup_build_notes_{sid}", None)
            st.rerun()

        if typical_pack:
            st.caption(f"**{setup_track}** · {typical_pack['character']} — {typical_pack['notes']}")
        if setup_source.startswith("telemetry"):
            fw = baseline.get("wing_setup_0")
            rw = baseline.get("wing_setup_1")
            wing_txt = f"FW/RW {fw:.0f}/{rw:.0f}" if fw is not None and rw is not None else "garage channels"
            st.caption(f"Session garage base: **{setup_source}** ({wing_txt}). Builder tweaks from this.")
        elif baseline:
            st.caption("Session garage base: imported setup snapshot (re-import CSV to refresh from telemetry).")

        if build_clicked:
            session_diag = build_session_diagnosis(
                df,
                best_lap=best_lap,
                conditions=setup_conditions,
                track=setup_track or track,
                track_length=track_length,
            )
            mode_key = setup_variant.lower()
            cur_run = best_run(load_session_runs(sid, APP_ROOT), mode_key)
            history = load_history(
                setup_track or track,
                mode_key,
                label_to_state(setup_wx),
                issue=session_diag.primary_issue,
                phase=session_diag.phase,
                compound=cur_run.compound if cur_run else None,
                app_root=APP_ROOT,
                before_session_id=sid,
            )
            base_mode = {"Session garage": "session", "Best verified": "best_verified", "Track typical": "typical"}[
                setup_base
            ]
            built = build_setup_from_practice(
                df,
                baseline,
                setup_track or track,
                variant=mode_key,
                lap=focus_lap,
                conditions=setup_conditions,
                diagnosis=session_diag,
                corner_cmp=corner_cmp,
                history=history,
                base=base_mode,
            )
            history_notes: list[str] = []
            if base_mode == "best_verified" and not history.best_verified:
                history_notes.append("No verified run on this track yet — started from the session garage instead.")
            bv = history.best_verified
            if bv and cur_run and bv["session_id"] != sid and base_mode != "best_verified":
                cur_pace = cur_run.best_corrected if mode_key == "quali" else cur_run.median_corrected
                if bv["pace"] < cur_pace - NOISE_FLOOR[mode_key]:
                    history_notes.append(
                        f"Session #{bv['session_id']} ran {cur_pace - bv['pace']:.3f}s faster (fuel-corrected) — "
                        "pick **Best verified** to start from that garage."
                    )
            save_recommendation(
                session_id=sid,
                track=setup_track or track,
                variant=mode_key,
                conditions=setup_conditions,
                base_setup=baseline,
                proposed_setup=built.setup,
                changes=built.changes,
                diagnosis={
                    "issue": session_diag.primary_issue,
                    "phase": session_diag.phase,
                    "strength": session_diag.strength,
                    "headline": session_diag.headline,
                    "balance": session_diag.symptoms,
                },
                app_root=APP_ROOT,
            )
            st.session_state[f"setup_coach_item_{sid}"] = setup_summary_item(
                session_diag, built.changes, built.findings
            )
            apply_setup_to_state(state_key, ui_id, built.setup)
            notes = list(built.findings)
            if built.diagnosis:
                notes.insert(0, f"Diagnosis: {built.diagnosis}.")
            if built.est_dt_vs_session is not None:
                notes.append(f"Est. vs your session setup: {built.est_dt_vs_session:+.3f}s")
            if built.est_dt_vs_typical is not None:
                notes.append(f"Est. vs track typical: {built.est_dt_vs_typical:+.3f}s")
            notes.extend(history_notes)
            notes.append(
                "Saved to the setup journal — import your next session on this track and it will be scored against this advice."
            )
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

        if not st.session_state.get(state_key) and typical_pack:
            apply_setup_to_state(state_key, ui_id, typical_pack["setup"])

        compare_base = baseline if baseline else normalize_setup(
            (typical_pack or {}).get("setup") or st.session_state.get(state_key) or {}
        )
        render_garage_tweaker(
            ui_id=ui_id,
            state_key=state_key,
            compare_base=compare_base,
            track=setup_track or track,
            reference_lap_time=float(focus_row["lap_time"]),
            base_label="session setup" if baseline else "baseline",
            chart_prefix=f"sess_{sid}",
            conditions=setup_conditions,
        )

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
            for tip in stint_saving_insights(
                df, focus_lap, reference_lap=ref_lap, conditions=session.get("conditions")
            ):
                css = {"tip": "insight-tip", "warning": "insight-warning", "info": "insight-info"}.get(
                    tip.severity, "insight-info"
                )
                st.markdown(
                    f'<div class="{css}"><strong>[{tip.category}] {tip.title}</strong><br/>{tip.detail}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")
        render_stint_windows_panel(
            df,
            track_length_m=float(track_length) if track_length else None,
            default_target_laps=None,
            chart_prefix=f"stint_{session['id']}",
        )

    with tab_coach:
        extra_setup: list[CoachItem] = []
        setup_item = st.session_state.get(f"setup_coach_item_{sid}")
        if setup_item is not None:
            extra_setup = [setup_item]

        extra_setup = extra_setup + setup_followup_items(followup_entries(sid, APP_ROOT))

        diag, top_items, rest_items = coach_feed_for_session(
            df,
            track=track,
            track_length=track_length,
            conditions=session.get("conditions"),
            extra_items=extra_setup or None,
            best_lap=best_lap,
        )
        render_coach_feed(diag.headline, top_items, rest_items)

        st.caption(
            "Session-level engineer feed from all probable laps (PB as reference). "
            "Lap selector still drives Corners, Compare, and Setup tabs."
        )


def render_garage() -> None:
    """Browse Quali/Race defaults for every catalog track — no session import required."""
    st.subheader("Garage")
    st.caption("Quali and race baselines for every calendar track. No session required.")

    tracks = list_tracks_with_setups()
    if not tracks:
        st.warning("No track setups available.")
        return

    raced_canon = {
        name
        for t in list_tracks(APP_ROOT)
        if (name := normalize_track_name(t))
    }

    if st.session_state.pop("garage_nav_pending", False):
        pending = st.session_state.get("garage_track")
        if pending in tracks:
            st.session_state["garage_track_select"] = pending

    g1, g2, g3, g4 = st.columns([1.3, 0.8, 1, 0.9])
    with g1:
        garage_track = st.selectbox(
            "Track",
            tracks,
            key="garage_track_select",
            format_func=lambda t: f"{t}  · raced" if t in raced_canon else t,
        )
    with g2:
        garage_variant = st.radio("Variant", ["Quali", "Race"], horizontal=True, key="garage_variant")
    with g3:
        garage_wx = st.selectbox("Track state", STATE_OPTIONS, index=0, key="garage_track_state")
        garage_conditions = compose_conditions(label_to_state(garage_wx))
    with g4:
        st.write("")
        st.write("")
        raced_label = "In your library" if garage_track in raced_canon else "Not raced yet"
        st.caption(raced_label)

    st.session_state["garage_track"] = garage_track
    wx_key = label_to_state(garage_wx)

    ui_id = f"g_{garage_track}_{garage_variant.lower()}_{wx_key}"
    state_key = f"garage_proposed_{garage_track}_{garage_variant.lower()}_{wx_key}"
    pack_key = f"garage_loaded_{garage_track}_{garage_variant.lower()}_{wx_key}"

    typical_pack = get_typical_setup(garage_track, garage_variant.lower(), conditions=garage_conditions)
    if typical_pack is None:
        st.error(f"No typical setup for {garage_track}.")
        return

    if not st.session_state.get(pack_key):
        apply_setup_to_state(state_key, ui_id, typical_pack["setup"])
        st.session_state[pack_key] = True

    st.caption(f"**{garage_track}** · {typical_pack['character']} — {typical_pack['notes']}")
    banner = weather_banner(wx_key)
    if banner:
        st.info(banner)

    if st.button(f"Reset to typical {garage_variant} ({garage_wx})", type="primary", key="garage_reset"):
        apply_setup_to_state(state_key, ui_id, typical_pack["setup"])
        st.session_state[pack_key] = True
        st.rerun()

    compare_base = normalize_setup(typical_pack["setup"])
    render_garage_tweaker(
        ui_id=ui_id,
        state_key=state_key,
        compare_base=compare_base,
        track=garage_track,
        reference_lap_time=None,
        base_label=f"typical {garage_variant.lower()} ({garage_wx})",
        chart_prefix=f"garage_{garage_track}_{garage_variant.lower()}_{wx_key}",
        conditions=garage_conditions,
    )


def render_strategy_planner() -> None:
    """Race strategy for any calendar track, built from every library session on it."""
    st.subheader("Strategy planner")
    st.caption(
        "Compound model, stop count, pit windows and safety-car calls from all your sessions on a track. "
        "Tracks you have not raced start from a manual model you fill in."
    )
    raced = sorted({name for t in list_tracks(APP_ROOT) if (name := normalize_track_name(t))})
    tracks = raced + [t for t in TRACK_LENGTHS_M if t not in raced]
    p1, p2 = st.columns([1.4, 1])
    track = p1.selectbox(
        "Track",
        tracks,
        key="planner_track",
        format_func=lambda t: f"{t}  · raced" if t in raced else t,
    )
    wx = p2.selectbox("Track state", STATE_OPTIONS, index=0, key="planner_state")
    state = label_to_state(wx)
    render_strategy(track, state, APP_ROOT, key=f"planner_{track}_{state}")


def main() -> None:
    init_db(APP_ROOT)
    ensure_progress_schema(APP_ROOT)
    ensure_session_meta_schema(APP_ROOT)

    st.markdown(
        '<p class="brand-mark">TELEMETRIA</p><p class="brand-sub">F1 26 · local telemetry desk</p>',
        unsafe_allow_html=True,
    )

    if "improbable_laps_scrubbed" not in st.session_state:
        scrubbed = scrub_improbable_lap_records(APP_ROOT)
        st.session_state["improbable_laps_scrubbed"] = scrubbed
        # Force progress re-index so PBs rebuild from probable laps only
        if scrubbed.get("pb_removed") or scrubbed.get("sessions_fixed"):
            st.session_state.pop("progress_backfilled", None)

    if "progress_backfilled" not in st.session_state:
        with st.spinner("Indexing progress from existing sessions…"):
            n = backfill_progress_from_library(APP_ROOT)
            st.session_state["progress_backfilled"] = n
    if "setup_fp_backfilled" not in st.session_state:
        st.session_state["setup_fp_backfilled"] = backfill_setup_fingerprints(APP_ROOT)
    if "session_tags_backfilled" not in st.session_state:
        # Blank type / track state only — tags you set are never touched.
        st.session_state["session_tags_backfilled"] = backfill_session_tags(APP_ROOT)
        if st.session_state["session_tags_backfilled"]:
            st.cache_data.clear()
            clear_tyre_cache()
    if "setup_journal_evaluated" not in st.session_state:
        with st.spinner("Scoring setup experiments…"):
            st.session_state["setup_journal_evaluated"] = evaluate_all(APP_ROOT)

    stats = library_stats(APP_ROOT)
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Sessions", stats["sessions"])
    s2.metric("Tracks", stats["tracks"])
    s3.metric("Library size", format_bytes(stats["stored_bytes"]))
    s4.metric("CSV space saved", format_bytes(max(0, stats["saved_bytes"])))

    modes = ["Browse sessions", "Track dossier", "Garage", "Strategy planner", "Import CSV"]
    if "sidebar_mode" not in st.session_state:
        st.session_state["sidebar_mode"] = "Browse sessions"
    # Honour dossier → Garage navigation
    if st.session_state.get("nav_mode") in modes:
        st.session_state["sidebar_mode"] = st.session_state.pop("nav_mode")

    with st.sidebar:
        st.header("Navigate")
        mode = st.radio(
            "Mode",
            modes,
            key="sidebar_mode",
        )
        if mode == "Import CSV":
            sidebar_import()
            st.stop()
        if mode in ("Track dossier", "Garage", "Strategy planner"):
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
                st.session_state.pop("setup_journal_evaluated", None)
                st.cache_data.clear()
                clear_tyre_cache()
                clear_run_cache()
                st.rerun()

    if mode == "Track dossier":
        render_dossier()
        return

    if mode == "Garage":
        render_garage()
        return

    if mode == "Strategy planner":
        render_strategy_planner()
        return

    with st.spinner("Loading compact telemetry…"):
        df = cached_session_df(
            int(session["id"]),
            session["telemetry_path"],
            int(session.get("stored_size_bytes") or 0),
        )

    summary = build_lap_summary(df, track_length=session.get("track_length"))
    if summary.empty:
        st.error(
            "Session has no probable completed laps "
            "(takebacks / red-flag shorts under 45s are ignored)."
        )
        st.stop()

    outline = get_track_outline(session["track"], APP_ROOT) if session.get("track") else None
    render_analysis(session, df, summary, outline)


if __name__ == "__main__":
    main()
