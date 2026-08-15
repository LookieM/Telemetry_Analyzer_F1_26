"""Race-engineer callouts from corner phase deltas (pure analysis + optional UI)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Columns useful in the Corners phase table (integrator / render helper).
PHASE_DISPLAY_COLS = [
    "corner_name",
    "kind",
    "time_s",
    "delta_s",
    "brake_point_m",
    "delta_brake_point_m",
    "turn_in_speed",
    "delta_turn_in_speed",
    "vmin",
    "delta_vmin",
    "exit_speed",
    "delta_exit_speed",
    "throttle_on_m",
    "delta_throttle_on_m",
    "trail_brake_s",
    "delta_trail_brake_s",
]


@dataclass
class CornerCallout:
    corner_id: str
    corner_name: str
    delta_s: float
    sentence: str
    severity: str  # tip | warning | info


def _f(row: pd.Series, key: str) -> float | None:
    if key not in row.index:
        return None
    v = row[key]
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def engineer_sentence(row: pd.Series) -> str:
    """
    One engineer sentence for a compared corner row (focus vs reference).

    Uses phase Δ columns from compare_corners. Positive delta_s = slower.
    """
    name = str(row.get("corner_name") or row.get("corner_id") or "Corner")
    bits: list[str] = []

    d_brake = _f(row, "delta_brake_point_m")
    d_vmin = _f(row, "delta_vmin")
    d_vmin_m = _f(row, "delta_vmin_m")
    d_exit = _f(row, "delta_exit_speed")
    d_thr = _f(row, "delta_throttle_on_m")
    d_turn = _f(row, "delta_turn_in_speed")
    d_trail = _f(row, "delta_trail_brake_s")
    d_t = _f(row, "delta_s")

    # Entry markers
    if d_brake is not None and abs(d_brake) >= 4:
        bits.append(f"{'later' if d_brake > 0 else 'earlier'} brake by {abs(d_brake):.0f} m")
    if d_turn is not None and abs(d_turn) >= 3:
        bits.append(f"turn-in {'+' if d_turn > 0 else ''}{d_turn:.0f} km/h")

    # Mid / apex
    late_apex = d_vmin_m is not None and d_vmin_m > 6
    early_apex = d_vmin_m is not None and d_vmin_m < -6
    if d_vmin is not None and abs(d_vmin) >= 2.5:
        bits.append(f"min speed {'+' if d_vmin > 0 else ''}{d_vmin:.0f} km/h")
    if late_apex:
        bits.append("later apex")
    elif early_apex:
        bits.append("earlier apex")

    if d_trail is not None and abs(d_trail) >= 0.08:
        bits.append(f"{'more' if d_trail > 0 else 'less'} trail-brake ({d_trail:+.2f}s)")

    # Exit
    early_throttle = d_thr is not None and d_thr < -5
    late_throttle = d_thr is not None and d_thr > 5
    if early_throttle:
        bits.append(f"earlier throttle ({abs(d_thr):.0f} m)")
    elif late_throttle:
        bits.append(f"later throttle-on ({d_thr:.0f} m)")
    if d_exit is not None and abs(d_exit) >= 3:
        bits.append(f"exit {'+' if d_exit > 0 else ''}{d_exit:.0f} km/h")

    # Diagnosis from pattern combos
    diagnosis = None
    if late_apex and early_throttle and (d_exit is None or d_exit < -1):
        diagnosis = "late apex + early throttle → exit understeer / parked mid-corner"
    elif early_throttle and d_exit is not None and d_exit < -3:
        diagnosis = "picking up throttle early is killing exit speed"
    elif late_throttle and (d_exit is None or d_exit < 0):
        diagnosis = "hesitant on exit — commit earlier, progressive throttle"
    elif d_brake is not None and d_brake < -8 and d_vmin is not None and d_vmin < -2:
        diagnosis = "early brake + lower min speed — leave braking later, carry entry"
    elif d_brake is not None and d_brake > 8 and d_vmin is not None and d_vmin < -3:
        diagnosis = "late brake but still slow mid-corner — check lock-up / turn-in"
    elif d_trail is not None and d_trail < -0.12 and d_vmin is not None and d_vmin < -2:
        diagnosis = "releasing brakes too early — trail a touch longer to the apex"
    elif d_trail is not None and d_trail > 0.15 and early_throttle:
        diagnosis = "long trail-brake into early throttle — car may push on exit"
    elif d_turn is not None and d_turn < -5 and (d_t is None or d_t > 0.02):
        diagnosis = "slow turn-in — rotate earlier or free the front on entry"

    if not bits and diagnosis is None:
        if d_t is not None and d_t > 0.02:
            return f"{name}: losing {d_t:.3f}s — phase deltas are small; check mini-sectors / ERS."
        return f"{name}: close to reference on entry/mid/exit markers."

    head = f"{name}: " + ", ".join(bits) if bits else f"{name}:"
    if diagnosis:
        return f"{head} → {diagnosis}."
    if d_t is not None and abs(d_t) >= 0.02:
        return f"{head} ({d_t:+.3f}s)."
    return head + "."


def corner_engineer_callouts(
    compared: pd.DataFrame,
    top_n: int = 3,
    min_delta_s: float = 0.02,
) -> list[CornerCallout]:
    """Worst time-loss corners with engineer sentences (phase Δ fallback)."""
    if compared.empty:
        return []
    if "kind" in compared.columns:
        corners = compared[compared["kind"] == "corner"].copy()
    else:
        corners = compared.copy()
    if corners.empty:
        corners = compared.copy()

    if "delta_s" in corners.columns:
        timed = corners[corners["delta_s"].notna() & (corners["delta_s"] >= min_delta_s)]
    else:
        timed = corners.iloc[0:0]

    if not timed.empty:
        pick = timed.sort_values("delta_s", ascending=False).head(top_n)
    else:
        # No clear time loss — still surface biggest phase disagreements
        score = pd.Series(0.0, index=corners.index)
        for col, weight in (
            ("delta_brake_point_m", 0.02),
            ("delta_vmin", 0.08),
            ("delta_exit_speed", 0.08),
            ("delta_throttle_on_m", 0.02),
            ("delta_trail_brake_s", 2.0),
            ("delta_turn_in_speed", 0.06),
        ):
            if col in corners.columns:
                score = score + corners[col].fillna(0).abs() * weight
        corners = corners.assign(_phase_score=score)
        pick = corners[corners["_phase_score"] >= 0.35].sort_values("_phase_score", ascending=False).head(top_n)
        if pick.empty:
            return []

    out: list[CornerCallout] = []
    for _, row in pick.iterrows():
        ds = float(row["delta_s"]) if "delta_s" in row.index and pd.notna(row.get("delta_s")) else 0.0
        sev = "warning" if ds >= 0.12 else "tip"
        out.append(
            CornerCallout(
                corner_id=str(row.get("corner_id", "")),
                corner_name=str(row.get("corner_name", "")),
                delta_s=ds,
                sentence=engineer_sentence(row),
                severity=sev,
            )
        )
    return out


def phase_table_for_display(compared: pd.DataFrame) -> pd.DataFrame:
    """Compact phase + Δ table for UI dataframes."""
    if compared.empty:
        return compared
    cols = [c for c in PHASE_DISPLAY_COLS if c in compared.columns]
    extra = [c for c in compared.columns if c not in cols and c.startswith(("delta_", "ref_"))]
    # Prefer curated order, then keep id/kind helpers
    base = [c for c in ("corner_id",) if c in compared.columns and c not in cols]
    return compared[base + cols].copy()


def format_phase_row(row: pd.Series) -> str:
    """Short markdown line for one corner's phase snapshot."""
    parts = [f"**{row.get('corner_name', row.get('corner_id', '?'))}**"]
    if _f(row, "delta_s") is not None:
        parts.append(f"{_f(row, 'delta_s'):+.3f}s")
    bp = _f(row, "brake_point_m")
    dbp = _f(row, "delta_brake_point_m")
    if bp is not None:
        delta = f" ({dbp:+.0f} m)" if dbp is not None else ""
        parts.append(f"brake @ {bp:.0f} m{delta}")
    vmin = _f(row, "vmin")
    if vmin is not None:
        dv = _f(row, "delta_vmin")
        delta = f" ({dv:+.0f})" if dv is not None else ""
        parts.append(f"vmin {vmin:.0f}{delta} km/h")
    ex = _f(row, "exit_speed")
    if ex is not None:
        de = _f(row, "delta_exit_speed")
        delta = f" ({de:+.0f})" if de is not None else ""
        parts.append(f"exit {ex:.0f}{delta} km/h")
    return " · ".join(parts)


def render_corner_engineer_panel(
    compared: pd.DataFrame,
    *,
    title: str = "Engineer — corner phases",
    top_n: int = 3,
    show_table: bool = True,
) -> None:
    """
    Streamlit helper for Corners / Coach tabs.

    Integrator: call after compare_corners(...). Safe no-op if streamlit missing
    or compared is empty.
    """
    try:
        import streamlit as st
    except ImportError:
        return

    if compared is None or compared.empty:
        st.caption("No corner phase comparison available.")
        return

    st.subheader(title)
    callouts = corner_engineer_callouts(compared, top_n=top_n)
    if callouts:
        for c in callouts:
            css = {
                "tip": "insight-tip",
                "warning": "insight-warning",
                "info": "insight-info",
            }.get(c.severity, "insight-info")
            st.markdown(
                f'<div class="{css}"><strong>{c.corner_name} ({c.delta_s:+.3f}s)</strong><br/>{c.sentence}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("No clear time-loss corners vs reference (or deltas below threshold).")

    if show_table:
        table = phase_table_for_display(compared)
        show = table.copy()
        for col in show.columns:
            if col in ("corner_id", "corner_name", "kind"):
                continue
            if show[col].dtype == object:
                continue
            show[col] = show[col].map(lambda x: f"{x:.3f}" if pd.notna(x) else "—")
        st.dataframe(show, use_container_width=True, hide_index=True)
