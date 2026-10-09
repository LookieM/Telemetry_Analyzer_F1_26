"""Streamlit Tyres tab: lap trace per wheel, car grid, stints, pressure calculator, compound model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from .channels import CAR_LAYOUT, WHEELS, primary_tyre_temp, surface_tyre_temp, temp_kind, wheel_columns
from .compounds import ACTUAL_COMPOUNDS, SLICK_CODES, Allocation, clear_allocation, get_allocation, set_allocation, softness
from .conditions import _as_state
from .corners import normalize_track_name
from .lap_views import corner_bands, lap_length
from .setup_tweaker import PA_PER_PSI
from .tyres import (
    StintSummary,
    TyreTargets,
    default_wear_limit,
    get_targets,
    library_race_stats,
    pressure_recommendation,
    save_targets,
    summarize_stints,
    track_compound_model,
    tyre_stints,
)
from .ui import palette
from .ui.uplot import distance_grid, pane, resample_by_distance, series, stint_timeline, trace_chart

WEAR_LIMIT_KEY = "tyre_wear_limit"


def wear_limit() -> float:
    """The wear limit the user set on the Tyres tab, else where they usually box (library)."""
    if WEAR_LIMIT_KEY in st.session_state:
        return float(st.session_state[WEAR_LIMIT_KEY])
    return default_wear_limit(library_race_stats())


def _fmt(v: Any, spec: str = ".1f", unit: str = "") -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v:{spec}}{unit}"


def stint_rows(summaries: list[StintSummary], alloc: Allocation, *, light_hard: bool = True) -> list[dict[str, Any]]:
    """stint_timeline segments for one session."""
    out = []
    for s in summaries:
        code = s.stint.compound
        out.append(
            {
                "from": s.stint.laps[0],
                "to": s.stint.laps[-1],
                "color": alloc.color(code),
                "text": alloc.role(code) or alloc.label(code),
                "title": f"{alloc.label(code)} · L{s.stint.laps[0]}–{s.stint.laps[-1]}",
                "light": light_hard and alloc.role(code) == "H",
            }
        )
    return out


# --------------------------------------------------------------------------- car grid


def _temp_color(t: float | None, targets: TyreTargets) -> str:
    if t is None or not np.isfinite(t):
        return "#8A9099"
    if t < targets.temp_lo:
        return "#3E7CC9"
    if t > targets.temp_hi:
        return "#D7263D"
    return "#2E9E44"


def render_car_grid(row: pd.Series, targets: TyreTargets, wear_rate: dict[str, float | None]) -> None:
    """FL FR / RL RR cards: lap-mean temperature vs window, peak, hot pressure, wear."""
    cards = []
    for i in CAR_LAYOUT:
        w = WHEELS[i]
        t = row.get(f"T_{w}")
        color = _temp_color(t, targets)
        target = targets.hot_target(i)
        p = row.get(f"P_{w}")
        p_txt = _fmt(p, ".1f", " psi") + (f" <span style='opacity:.65'>(target {target:.1f})</span>" if target else "")
        cards.append(
            f"""
            <div style="border-left:6px solid {color};padding:6px 10px;border-radius:6px;
                        background:rgba(128,128,128,0.08)">
              <div style="font-size:11px;font-weight:700;letter-spacing:.06em;opacity:.75">{w}</div>
              <div style="font-size:22px;font-weight:700;font-variant-numeric:tabular-nums">{_fmt(t, ".0f", " °C")}</div>
              <div style="font-size:12px;opacity:.85;font-variant-numeric:tabular-nums">
                peak {_fmt(row.get(f"Tpk_{w}"), ".0f", " °C")} · in window {_fmt(row.get(f"Twin_{w}"), ".0f", "%")}<br/>
                {p_txt}<br/>
                wear {_fmt(row.get(f"W_{w}"), ".1f", "%")} · {_fmt(wear_rate.get(w), ".2f", " %/lap")} this stint
              </div>
            </div>"""
        )
    st.html(
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;max-width:560px">' + "".join(cards) + "</div>"
    )
    st.caption(
        f"Colour = lap-mean temperature vs the {targets.temp_lo:.0f}–{targets.temp_hi:.0f} °C window "
        "(blue cold · green in window · red hot)."
    )


# --------------------------------------------------------------------------- charts


def tyre_lap_trace(
    df: pd.DataFrame,
    focus_df: pd.DataFrame,
    *,
    key: str,
    targets: TyreTargets,
    corners: Any,
    cursor: float | None,
    step_m: float = 2.0,
) -> float | None:
    """Per-wheel temperatures, hot pressure, wear, brakes and slip over one lap (cursor shared with the map)."""
    length = lap_length(focus_df)
    temp = primary_tyre_temp(df)
    surface = surface_tyre_temp(df)
    if surface and temp and surface[1] == temp[1]:
        surface = None  # only one temperature channel in this export
    brakes = wheel_columns(df, "brake_temp")
    press = wheel_columns(df, "tyre_press")
    wear = wheel_columns(df, "tyre_wear")
    if length is None or not (temp or press or wear):
        return trace_chart([], [], key=key, empty_text="No tyre channels on this lap.")
    grid = distance_grid(length, step_m)
    cols = [*(temp[1] if temp else []), *(surface[1] if surface else []), *(brakes or []), *(press or []), *(wear or []), "slip_max", "speed"]
    f = resample_by_distance(focus_df, cols, grid)
    panes = []
    if temp:
        lines = [series(WHEELS[i], f[c], color=palette.WHEEL[i]) for i, c in enumerate(temp[1])]
        lines += [
            series("window lo", np.full(len(grid), targets.temp_lo), color=palette.NEUTRAL, dash=True, width=1),
            series("window hi", np.full(len(grid), targets.temp_hi), color=palette.NEUTRAL, dash=True, width=1),
        ]
        panes.append(pane(temp[0], lines, unit="°C", height=170, decimals=0))
    if surface:
        panes.append(
            pane(surface[0], [series(WHEELS[i], f[c], color=palette.WHEEL[i]) for i, c in enumerate(surface[1])], unit="°C", height=120, decimals=0)
        )
    if brakes:
        panes.append(
            pane("Brake temp", [series(WHEELS[i], f[c], color=palette.WHEEL[i]) for i, c in enumerate(brakes)], unit="°C", height=110, decimals=0)
        )
    if press:
        panes.append(
            pane(
                "Hot pressure",
                [series(WHEELS[i], f[c] / PA_PER_PSI, color=palette.WHEEL[i], decimals=2) for i, c in enumerate(press)],
                unit="psi",
                height=130,
                decimals=2,
                axis_decimals=1,
            )
        )
    if wear:
        panes.append(
            pane(
                "Wear",
                [series(WHEELS[i], f[c] * 100, color=palette.WHEEL[i]) for i, c in enumerate(wear)],
                unit="%",
                height=110,
            )
        )
    if "slip_max" in focus_df.columns:
        panes.append(pane("Max wheel slip", [series("slip", f["slip_max"], color=palette.BRAKE, decimals=3)], height=90, decimals=3, axis_decimals=2))
    panes.append(pane("Speed", [series("Speed", f["speed"], color=palette.FOCUS)], unit="km/h", height=90, decimals=0))
    return trace_chart(grid, panes, key=key, bands=corner_bands(corners), cursor_x=cursor, sync="lap")


def stint_charts(tbl: pd.DataFrame, summaries: list[StintSummary], alloc: Allocation, *, key: str) -> None:
    """Lap-by-lap view of the session: corrected pace with stint fits, wear, temps, pressures."""
    if tbl.empty:
        return
    laps = tbl["lap"].to_numpy(dtype=float)
    push = (tbl["lap_class"] == "push").to_numpy()
    pace_lines = [
        series("other laps", np.where(~push, tbl["corr_time"], np.nan), color=palette.NEUTRAL, mode="points", size=6, hollow=True, decimals=3),
    ]
    for s in summaries:
        code = s.stint.compound
        in_stint = tbl["lap"].isin(s.stint.laps).to_numpy()
        pace_lines.append(
            series(
                f"S{s.stint.idx + 1} {alloc.label(code)}",
                np.where(in_stint & push, tbl["corr_time"], np.nan),
                color=alloc.color(code),
                mode="points",
                size=7,
                decimals=3,
            )
        )
        if s.deg.slope is not None:
            fit = s.deg.intercept + s.deg.slope * tbl["age"].astype(float)
            pace_lines.append(
                series(f"S{s.stint.idx + 1} trend {s.deg.slope:+.3f}s/lap", np.where(in_stint, fit, np.nan), color=alloc.color(code), dash=True, width=1.5, decimals=3)
            )
    # Keep the pace axis on the push laps (pit laps would squash it).
    corr = tbl.loc[push, "corr_time"]
    pace_range = [float(corr.min()) - 0.5, float(corr.max()) + 0.8] if not corr.empty else None
    panes = [pane("Lap time, fuel-corrected to 5 kg", pace_lines, unit="s", height=200, decimals=3, axis_decimals=1, **({"range": pace_range} if pace_range else {}))]
    for prefix, title, unit, dec in (("W_", "Wear (end of lap)", "%", 1), ("T_", "Tyre temp (lap mean)", "°C", 0), ("P_", "Hot pressure (lap median)", "psi", 2)):
        if f"{prefix}FL" not in tbl.columns:
            continue
        panes.append(
            pane(
                title,
                [series(w, tbl[f"{prefix}{w}"], color=palette.WHEEL[i], decimals=dec) for i, w in enumerate(WHEELS)],
                unit=unit,
                height=120,
                decimals=dec,
                axis_decimals=0 if dec == 0 else 1,
            )
        )
    bands = [
        {"from": s.stint.laps[0] - 0.5, "to": s.stint.laps[-1] + 0.5, "label": f"S{s.stint.idx + 1} {alloc.label(s.stint.compound)}", "color": alloc.color(s.stint.compound)}
        for s in summaries
    ]
    markers = [{"x": float(r["lap"]), "label": "PIT"} for _, r in tbl[tbl["lap_class"] == "pit"].iterrows()]
    trace_chart(laps, panes, key=key, x_label="Lap", bands=bands, markers=markers, sync="stint")


def stint_table(summaries: list[StintSummary], alloc: Allocation) -> pd.DataFrame:
    rows = []
    for s in summaries:
        st_ = s.stint
        lim = s.limiting_wheel
        front = [s.temp_mean.get(w) for w in ("FL", "FR") if s.temp_mean.get(w) is not None]
        rear = [s.temp_mean.get(w) for w in ("RL", "RR") if s.temp_mean.get(w) is not None]
        rows.append(
            {
                "Stint": st_.idx + 1,
                "Compound": alloc.label(st_.compound),
                "Laps": f"{st_.laps[0]}–{st_.laps[-1]} ({st_.n_laps})",
                "Push laps": len(st_.push_laps),
                "Deg (s/lap)": round(s.deg.slope, 3) if s.deg.slope is not None else None,
                "R²": round(s.deg.r2, 2) if s.deg.r2 is not None else None,
                "Cliff at age": str(s.deg.cliff_age) if s.deg.cliff_age is not None else "—",
                "Limiting": lim,
                "Wear (%/lap)": round(s.wear_rate[lim], 2) if lim and s.wear_rate.get(lim) is not None else None,
                "Max wear (%)": round(s.wear_now, 1) if s.wear_now is not None else None,
                f"Laps to {wear_limit():.0f}%": round(s.laps_to_limit, 1) if s.laps_to_limit is not None else None,
                "Warm-up (s)": round(s.warmup_s, 2) if s.warmup_s is not None else None,
                "Fuel (kg/lap)": round(s.fuel_per_lap, 2) if s.fuel_per_lap is not None else None,
                "T front / rear (°C)": f"{np.mean(front):.0f} / {np.mean(rear):.0f}" if front and rear else None,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- pressures + model


def render_pressures(summary: StintSummary, targets: TyreTargets, alloc: Allocation, app_root: Path, key: str) -> None:
    code = summary.stint.compound
    st.markdown(f"**Pressures & window — {alloc.label(code)}** (stint {summary.stint.idx + 1}, push laps only)")
    hot = summary.hot_psi
    meas_front = np.nanmean([hot.get("FL") or np.nan, hot.get("FR") or np.nan])
    meas_rear = np.nanmean([hot.get("RL") or np.nan, hot.get("RR") or np.nan])
    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 0.8])
    lo = c1.number_input("Window low (°C)", 20.0, 150.0, float(targets.temp_lo), 1.0, key=f"{key}_lo")
    hi = c2.number_input("Window high (°C)", 20.0, 160.0, float(targets.temp_hi), 1.0, key=f"{key}_hi")
    front = c3.number_input(
        "Hot target front (psi)",
        10.0,
        40.0,
        float(targets.hot_front_psi or (meas_front if np.isfinite(meas_front) else 22.0)),
        0.1,
        key=f"{key}_hf",
        help="Defaults to what the fronts ran hot this stint — set your own target.",
    )
    rear = c4.number_input(
        "Hot target rear (psi)",
        10.0,
        40.0,
        float(targets.hot_rear_psi or (meas_rear if np.isfinite(meas_rear) else 22.0)),
        0.1,
        key=f"{key}_hr",
    )
    c5.write("")
    if c5.button("Save targets", key=f"{key}_save", disabled=code is None):
        save_targets(TyreTargets(code, lo, hi, front, rear, "saved"), app_root)
        st.success(f"Saved targets for {alloc.label(code)}.")
    live = TyreTargets(code, lo, hi, front, rear)
    rec = pressure_recommendation(hot, summary.cold_psi, live)
    show = rec.copy()
    for col in show.columns[1:]:
        show[col] = show[col].map(lambda v: "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:+.1f}" if "Change" in col or "Build" in col else f"{v:.1f}")
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.caption("Cold set needed = cold set now + (hot target − hot measured). The game's build-up is small (~0–1 psi).")


def render_allocation_editor(track: str, alloc: Allocation, app_root: Path, key: str) -> None:
    st.caption(f"S/M/H for {track}: **{alloc.source}** — " + ", ".join(f"{ACTUAL_COMPOUNDS[c]}={r}" for c, r in sorted(alloc.roles.items(), key=lambda kv: -softness(kv[0]))) if alloc.roles else f"S/M/H for {track}: unknown")
    codes = sorted(SLICK_CODES, key=softness, reverse=True)
    names = ["—"] + [ACTUAL_COMPOUNDS[c] for c in codes]
    inv = {r: c for c, r in alloc.roles.items()}
    cols = st.columns(5)
    picks = []
    for col, role in zip(cols[:3], ("S", "M", "H")):
        cur = inv.get(role)
        idx = names.index(ACTUAL_COMPOUNDS[cur]) if cur in ACTUAL_COMPOUNDS else 0
        pick = col.selectbox(f"{role}", names, index=idx, key=f"{key}_{role}")
        picks.append(None if pick == "—" else next(c for c in codes if ACTUAL_COMPOUNDS[c] == pick))
    cols[3].write("")
    if cols[3].button("Save S/M/H", key=f"{key}_save"):
        set_allocation(track, *picks, app_root=app_root)
        st.rerun()
    cols[4].write("")
    if cols[4].button("Use inferred", key=f"{key}_clear"):
        clear_allocation(track, app_root)
        st.rerun()


def compound_model_table(model) -> pd.DataFrame:
    rows = []
    for c, m in sorted(model.compounds.items(), key=lambda kv: -softness(kv[0])):
        rows.append(
            {
                "Compound": m.label,
                "Offset vs ref (s)": round(m.offset_s, 3),
                "Deg (s/lap)": round(m.deg_s_per_lap, 3),
                "Wear (%/lap)": round(m.wear_pct_per_lap, 2) if m.wear_pct_per_lap else None,
                f"Max laps @ {wear_limit():.0f}%": m.max_laps(wear_limit()),
                "Warm-up (s)": round(m.warmup_s, 2),
                "Stints / laps": f"{m.n_stints} / {m.n_laps}",
                "Source": m.source,
                "Note": m.note,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- tab


def render_tyres_tab(
    session: dict[str, Any],
    df: pd.DataFrame,
    summary: pd.DataFrame,
    *,
    focus_lap: int,
    focus_df: pd.DataFrame,
    corners: Any,
    cursor: float | None,
    app_root: Path,
) -> float | None:
    """Returns a clicked lap distance (to pin the shared cursor), else None."""
    sid = int(session["id"])
    track = normalize_track_name(session.get("track")) or (session.get("track") or "")
    alloc = get_allocation(track, app_root)

    top = st.columns([1, 1, 1, 1, 1, 1.1])
    stints = tyre_stints(summary)
    focus_stint = next((s for s in stints if focus_lap in s.laps), stints[0] if stints else None)
    if focus_stint is None:
        st.info("No tyre stints found in this session.")
        return None
    temp_src = primary_tyre_temp(df)
    targets = get_targets(focus_stint.compound, app_root, kind=temp_kind(temp_src[0] if temp_src else None))
    stats = library_race_stats(app_root)
    summaries, tbl = summarize_stints(
        df, summary, session=session, wear_limit=wear_limit(), targets=targets, fuel_k=stats.fuel_s_per_kg
    )
    focus_s = next(s for s in summaries if s.stint.idx == focus_stint.idx)
    lim = focus_s.limiting_wheel

    top[0].metric("Compound", alloc.label(focus_s.stint.compound))
    top[1].metric("Tyre age", f"{focus_s.stint.ages.get(focus_lap, 0)} laps", help="Laps on this set before the focus lap.")
    top[2].metric("Degradation", _fmt(focus_s.deg.slope, "+.3f", " s/lap"), help=f"Fuel-corrected, push laps · R² {_fmt(focus_s.deg.r2, '.2f')}")
    top[3].metric(f"Wear ({lim or '—'})", _fmt(focus_s.wear_rate.get(lim) if lim else None, ".2f", " %/lap"))
    top[4].metric(f"Laps to {wear_limit():.0f}%", _fmt(focus_s.laps_to_limit, ".1f"))
    top[5].number_input("Wear limit (%)", 30.0, 95.0, wear_limit(), 1.0, key=WEAR_LIMIT_KEY, help="Max-wheel wear treated as the end of a stint (tyres and strategy).")

    stint_timeline([{"label": "This session", "stints": stint_rows(summaries, alloc)}], laps_total=int(tbl["lap"].max()) + 1, key=f"tyre_tl_{sid}")

    left, right = st.columns([1.5, 1])
    with left:
        clicked = tyre_lap_trace(df, focus_df, key=f"tyre_trace_{sid}", targets=targets, corners=corners, cursor=cursor)
    with right:
        row = tbl[tbl["lap"] == focus_lap]
        if not row.empty:
            st.markdown(f"**Lap {focus_lap}** · {row.iloc[0]['lap_class']} lap")
            render_car_grid(row.iloc[0], targets, focus_s.wear_rate)
        src = primary_tyre_temp(df)
        if src:
            st.caption(f"Temperature channel: {src[0]}.")

    st.markdown("#### Stints")
    st.dataframe(stint_table(summaries, alloc), use_container_width=True, hide_index=True)
    stint_charts(tbl, summaries, alloc, key=f"tyre_stints_{sid}")
    st.caption(
        f"Lap times corrected to 5 kg with {stats.fuel_s_per_kg:.3f} s/kg (fuel + track evolution, "
        + (f"measured from {stats.fuel_pairs} same-compound stint pairs in your races" if stats.fuel_pairs else "default")
        + "). Hollow points = start / in / pit / out / SC / slow laps, left out of the trends. Drag to zoom, double-click to reset."
    )

    with st.expander("Pressures & operating window", expanded=False):
        render_pressures(focus_s, targets, alloc, app_root, key=f"press_{sid}_{focus_s.stint.compound}")

    with st.expander(f"Compound model — {track} (all library sessions)", expanded=False):
        state = _as_state(session.get("conditions"))
        model = track_compound_model(track, state, app_root, wear_limit=wear_limit())
        if not model.compounds:
            st.caption("Not enough long runs on this track yet (need ≥4 push laps on one set).")
        else:
            st.dataframe(compound_model_table(model), use_container_width=True, hide_index=True)
            meas = f"{model.pit_loss:.1f} s from {len(model.pit_losses)} stop(s)" if model.pit_loss else "not measured yet"
            st.caption(
                f"Reference compound: {alloc.label(model.ref_compound)} · base pace {_fmt(model.base_pace_s, '.3f', ' s')} "
                f"(new tyre, 5 kg) · pit loss {meas} · sessions used: {', '.join(f'#{i}' for i in model.sources) or '—'}."
            )
        render_allocation_editor(track, alloc, app_root, key=f"alloc_{sid}")
    return clicked
