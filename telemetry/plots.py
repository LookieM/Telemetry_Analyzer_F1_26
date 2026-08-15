"""Plotly figure builders for the Streamlit UI."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


DARK_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(17,24,39,0.6)",
    font=dict(family="Segoe UI, sans-serif", color="#e5e7eb"),
    margin=dict(l=40, r=20, t=40, b=40),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
)


def _x_axis(df: pd.DataFrame) -> tuple[np.ndarray, str]:
    if "lap_distance" in df.columns:
        return df["lap_distance"].to_numpy(), "Distance (m)"
    if "bin_index" in df.columns:
        return df["bin_index"].to_numpy(), "Track bin"
    return np.arange(len(df)), "Sample"


def pace_chart(summary: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if summary.empty:
        return fig
    colors = ["#22c55e" if b else "#38bdf8" for b in summary["is_best"]]
    fig.add_trace(
        go.Bar(
            x=summary["lap"],
            y=summary["lap_time"],
            marker_color=colors,
            text=[f"{t:.3f}" for t in summary["lap_time"]],
            textposition="outside",
            name="Lap time",
            hovertemplate="Lap %{x}<br>%{y:.3f}s<extra></extra>",
        )
    )
    best = summary.loc[summary["is_best"], "lap_time"].iloc[0]
    fig.add_hline(y=best, line_dash="dot", line_color="#22c55e", annotation_text="Best")
    fig.update_layout(**DARK_LAYOUT, title="Lap times", height=360, yaxis_title="Lap time (s)")
    return fig


def _map_xy(df: pd.DataFrame) -> tuple[str, str] | None:
    """Return horizontal map axes. F1/SRT world frame uses X/Y on the ground plane."""
    if "pos_x" in df.columns and "pos_y" in df.columns:
        return "pos_x", "pos_y"
    if "pos_x" in df.columns and "pos_z" in df.columns:
        # Legacy fallback if only X/Z were stored
        return "pos_x", "pos_z"
    return None


def track_outline_trace(outline: dict | None) -> go.Scatter | None:
    if not outline or not outline.get("x") or not outline.get("y"):
        return None
    return go.Scatter(
        x=outline["x"],
        y=outline["y"],
        mode="lines",
        line=dict(color="rgba(148,163,184,0.55)", width=6),
        name="Track",
        hoverinfo="skip",
        showlegend=False,
    )


def track_map(
    lap_df: pd.DataFrame,
    color: str | None = "speed",
    title: str = "Racing line",
    outline: dict | None = None,
    highlight_distance: float | None = None,
    corners: list | None = None,
) -> go.Figure:
    axes = _map_xy(lap_df)
    fig = go.Figure()
    outline_tr = track_outline_trace(outline)
    if outline_tr is not None:
        fig.add_trace(outline_tr)

    if lap_df.empty or axes is None:
        fig.update_layout(**DARK_LAYOUT, title=title, height=560)
        return fig

    x_col, y_col = axes
    color_vals = lap_df[color] if color and color in lap_df.columns else None
    dist = lap_df["lap_distance"] if "lap_distance" in lap_df.columns else np.arange(len(lap_df))
    custom = np.column_stack([dist, lap_df[x_col], lap_df[y_col]])

    fig.add_trace(
        go.Scatter(
            x=lap_df[x_col],
            y=lap_df[y_col],
            mode="lines+markers",
            line=dict(color="rgba(255,255,255,0.15)", width=2),
            marker=dict(
                size=4,
                color=color_vals if color_vals is not None else "#38bdf8",
                colorscale="Turbo",
                showscale=color_vals is not None,
                colorbar=dict(title=color or "") if color_vals is not None else None,
            ),
            name="Line",
            customdata=custom,
            hovertemplate="Dist %{customdata[0]:.0f} m<br>x=%{x:.1f}<br>y=%{y:.1f}<extra></extra>",
        )
    )

    # Corner apex labels
    if corners and "lap_distance" in lap_df.columns:
        for c in corners:
            apex = getattr(c, "apex", None)
            if apex is None or getattr(c, "kind", "") == "straight":
                continue
            idx = int(np.argmin(np.abs(lap_df["lap_distance"].to_numpy() - float(apex))))
            fig.add_trace(
                go.Scatter(
                    x=[float(lap_df[x_col].iloc[idx])],
                    y=[float(lap_df[y_col].iloc[idx])],
                    mode="markers+text",
                    marker=dict(size=8, color="#f8fafc", symbol="circle-open", line=dict(width=2, color="#e2e8f0")),
                    text=[getattr(c, "id", "")],
                    textposition="top center",
                    textfont=dict(size=10, color="#e2e8f0"),
                    name=getattr(c, "name", ""),
                    showlegend=False,
                    hovertemplate=f"{getattr(c, 'name', '')}<extra></extra>",
                )
            )

    if highlight_distance is not None and "lap_distance" in lap_df.columns:
        idx = int(np.argmin(np.abs(lap_df["lap_distance"].to_numpy() - float(highlight_distance))))
        fig.add_trace(
            go.Scatter(
                x=[float(lap_df[x_col].iloc[idx])],
                y=[float(lap_df[y_col].iloc[idx])],
                mode="markers",
                marker=dict(size=16, color="#f43f5e", line=dict(width=2, color="white"), symbol="circle"),
                name="Cursor",
                hovertemplate=f"Pinned · {highlight_distance:.0f} m<extra></extra>",
            )
        )

    fig.update_layout(
        **DARK_LAYOUT,
        title=title,
        height=560,
        xaxis=dict(scaleanchor="y", scaleratio=1, showgrid=False, zeroline=False, showticklabels=False, title=""),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
    )
    return fig


def delta_map(aligned: pd.DataFrame, outline: dict | None = None) -> go.Figure:
    axes = _map_xy(aligned)
    if aligned.empty or axes is None or "delta_time" not in aligned.columns:
        return track_map(pd.DataFrame(), title="Delta map", outline=outline)

    x_col, y_col = axes
    plot_df = aligned.copy()
    if "delta_gain" in plot_df.columns:
        plot_df["map_color"] = plot_df["delta_gain"]
        title = "Track map (green = gaining vs ref)"
        scale = "RdYlGn"
    else:
        plot_df["map_color"] = plot_df["delta_time"]
        title = "Track map (cumulative delta)"
        scale = "RdYlGn_r"

    fig = go.Figure()
    outline_tr = track_outline_trace(outline)
    if outline_tr is not None:
        fig.add_trace(outline_tr)

    fig.add_trace(
        go.Scatter(
            x=plot_df[x_col],
            y=plot_df[y_col],
            mode="markers",
            marker=dict(
                size=4,
                color=plot_df["map_color"],
                colorscale=scale,
                showscale=True,
                colorbar=dict(title="Δ"),
            ),
            name="Delta",
            hovertemplate="Δ=%{marker.color:.3f}<extra></extra>",
        )
    )
    fig.update_layout(
        **DARK_LAYOUT,
        title=title,
        height=560,
        xaxis=dict(scaleanchor="y", scaleratio=1, showgrid=False, zeroline=False, showticklabels=False, title=""),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
    )
    return fig


def track_library_map(outline: dict | None, title: str = "Circuit map") -> go.Figure:
    fig = go.Figure()
    tr = track_outline_trace(outline)
    if tr is not None:
        # Stronger outline for the library map view
        tr.line.color = "#38bdf8"
        tr.line.width = 3
        fig.add_trace(tr)
    fig.update_layout(
        **DARK_LAYOUT,
        title=title,
        height=420,
        xaxis=dict(scaleanchor="y", scaleratio=1, showgrid=False, zeroline=False, showticklabels=False, title=""),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
    )
    return fig


def single_lap_telemetry(
    lap_df: pd.DataFrame,
    corners: list | None = None,
    highlight_distance: float | None = None,
) -> go.Figure:
    x, x_title = _x_axis(lap_df)
    corner_labels = _corner_labels_for_x(x, corners) if corners else [""] * len(x)
    axes = _map_xy(lap_df)
    if axes and "lap_distance" in lap_df.columns:
        custom = np.column_stack(
            [
                lap_df["lap_distance"],
                lap_df[axes[0]],
                lap_df[axes[1]],
                corner_labels,
            ]
        )
    else:
        custom = np.column_stack([x, np.zeros(len(x)), np.zeros(len(x)), corner_labels])

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.4, 0.25, 0.2, 0.15],
        subplot_titles=("Speed", "Throttle / Brake", "Gear", "Steering"),
    )
    hover = "Dist %{customdata[0]:.0f} m<br>%{customdata[3]}<br>y=%{y:.2f}<extra>%{fullData.name}</extra>"

    if "speed" in lap_df.columns:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=lap_df["speed"],
                name="Speed",
                line=dict(color="#22d3ee", width=2),
                customdata=custom,
                hovertemplate=hover,
            ),
            row=1,
            col=1,
        )
    if "throttle" in lap_df.columns:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=lap_df["throttle"],
                name="Throttle",
                line=dict(color="#22c55e", width=2),
                customdata=custom,
                hovertemplate=hover,
            ),
            row=2,
            col=1,
        )
    if "brake" in lap_df.columns:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=lap_df["brake"],
                name="Brake",
                line=dict(color="#ef4444", width=2),
                customdata=custom,
                hovertemplate=hover,
            ),
            row=2,
            col=1,
        )
    if "gear" in lap_df.columns:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=lap_df["gear"],
                name="Gear",
                line=dict(color="#f59e0b", width=2, shape="vh"),
                customdata=custom,
                hovertemplate=hover,
            ),
            row=3,
            col=1,
        )
    if "steering" in lap_df.columns:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=lap_df["steering"],
                name="Steering",
                line=dict(color="#2dd4bf", width=2),
                customdata=custom,
                hovertemplate=hover,
            ),
            row=4,
            col=1,
        )

    _add_corner_vlines(fig, corners, rows=4)
    if highlight_distance is not None:
        for r in range(1, 5):
            fig.add_vline(
                x=highlight_distance,
                line_width=2,
                line_dash="dot",
                line_color="#f43f5e",
                row=r,
                col=1,
            )

    fig.update_layout(**DARK_LAYOUT, height=780, hovermode="x unified")
    fig.update_xaxes(title_text=x_title, row=4, col=1)
    fig.update_yaxes(range=[-0.05, 1.05], row=2, col=1)
    return fig


def telemetry_overlay(
    aligned: pd.DataFrame,
    ref_label: str,
    cmp_label: str,
    corners: list | None = None,
    highlight_distance: float | None = None,
) -> go.Figure:
    x, x_title = _x_axis(aligned)
    corner_labels = _corner_labels_for_x(x, corners) if corners else [""] * len(x)
    custom = np.column_stack([x, corner_labels])
    hover = "Dist %{customdata[0]:.0f} m · %{customdata[1]}<br>y=%{y:.2f}<extra>%{fullData.name}</extra>"

    fig = make_subplots(
        rows=5,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.28, 0.18, 0.18, 0.18, 0.18],
        subplot_titles=("Speed", "Throttle / Brake", "Delta (cmp − ref)", "Gear / RPM", "Steering"),
    )

    def _add(y, name, color, row, dash=None, shape=None):
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                name=name,
                line=dict(color=color, width=2, dash=dash, shape=shape or "linear"),
                customdata=custom,
                hovertemplate=hover,
            ),
            row=row,
            col=1,
        )

    if "ref_speed" in aligned.columns:
        _add(aligned["ref_speed"], f"Speed {ref_label}", "#38bdf8", 1)
    if "cmp_speed" in aligned.columns:
        _add(aligned["cmp_speed"], f"Speed {cmp_label}", "#f97316", 1)
    if "ref_throttle" in aligned.columns:
        _add(aligned["ref_throttle"], f"Thr {ref_label}", "#4ade80", 2)
    if "cmp_throttle" in aligned.columns:
        _add(aligned["cmp_throttle"], f"Thr {cmp_label}", "#86efac", 2, dash="dot")
    if "ref_brake" in aligned.columns:
        _add(aligned["ref_brake"], f"Brk {ref_label}", "#ef4444", 2)
    if "cmp_brake" in aligned.columns:
        _add(aligned["cmp_brake"], f"Brk {cmp_label}", "#fca5a5", 2, dash="dot")
    if "delta_time" in aligned.columns:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=aligned["delta_time"],
                name="Δ time",
                line=dict(color="#a78bfa", width=2),
                fill="tozeroy",
                customdata=custom,
                hovertemplate=hover,
            ),
            row=3,
            col=1,
        )
    if "ref_gear" in aligned.columns:
        _add(aligned["ref_gear"], f"Gear {ref_label}", "#fbbf24", 4, shape="vh")
    if "cmp_gear" in aligned.columns:
        _add(aligned["cmp_gear"], f"Gear {cmp_label}", "#fde68a", 4, dash="dot", shape="vh")
    if "ref_steering" in aligned.columns:
        _add(aligned["ref_steering"], f"Steer {ref_label}", "#2dd4bf", 5)
    if "cmp_steering" in aligned.columns:
        _add(aligned["cmp_steering"], f"Steer {cmp_label}", "#99f6e4", 5, dash="dot")

    _add_corner_vlines(fig, corners, rows=5)
    if highlight_distance is not None:
        for r in range(1, 6):
            fig.add_vline(
                x=highlight_distance,
                line_width=2,
                line_dash="dot",
                line_color="#f43f5e",
                row=r,
                col=1,
            )

    fig.update_layout(**DARK_LAYOUT, height=920, hovermode="x unified", title="Lap comparison telemetry")
    fig.update_xaxes(title_text=x_title, row=5, col=1)
    fig.update_yaxes(range=[-0.05, 1.05], row=2, col=1)
    return fig


def _corner_labels_for_x(x_vals, corners: list) -> list[str]:
    labels = []
    for xv in x_vals:
        name = ""
        for c in corners:
            if float(c.start) <= float(xv) < float(c.end):
                name = c.name
                break
        labels.append(name)
    return labels


def _add_corner_vlines(fig: go.Figure, corners: list | None, rows: int) -> None:
    if not corners:
        return
    for c in corners:
        if getattr(c, "kind", "") == "straight":
            continue
        for r in range(1, rows + 1):
            fig.add_vline(
                x=float(c.start),
                line_width=1,
                line_dash="dot",
                line_color="rgba(148,163,184,0.35)",
                row=r,
                col=1,
            )


def corner_delta_bars(compared: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if compared.empty or "delta_s" not in compared.columns:
        fig.update_layout(**DARK_LAYOUT, title="Corner delta", height=360)
        return fig
    data = compared[compared["kind"] == "corner"].copy() if "kind" in compared.columns else compared.copy()
    colors = ["#22c55e" if v < 0 else "#ef4444" for v in data["delta_s"].fillna(0)]
    fig.add_trace(
        go.Bar(
            x=data["corner_id"],
            y=data["delta_s"],
            marker_color=colors,
            text=[f"{v:+.3f}" if pd.notna(v) else "" for v in data["delta_s"]],
            textposition="outside",
            hovertemplate="%{x}<br>%{y:+.3f}s<extra></extra>",
        )
    )
    fig.update_layout(**DARK_LAYOUT, title="Corner time loss (focus − reference)", height=380, yaxis_title="Δs")
    return fig


def pb_history_chart(history: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if history.empty:
        fig.update_layout(**DARK_LAYOUT, title="Personal best history", height=340)
        return fig
    h = history.sort_values("set_at")
    fig.add_trace(
        go.Scatter(
            x=h["set_at"],
            y=h["lap_time"],
            mode="lines+markers",
            line=dict(color="#22c55e", width=2),
            marker=dict(size=9),
            name="PB progression",
            hovertemplate="%{x}<br>%{y:.3f}s<extra></extra>",
        )
    )
    fig.update_layout(**DARK_LAYOUT, title="Personal best progression", height=340, yaxis_title="Lap time (s)")
    return fig


def session_bests_chart(sessions: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if sessions.empty or "best_lap_time" not in sessions.columns:
        fig.update_layout(**DARK_LAYOUT, title="Session bests", height=340)
        return fig
    s = sessions.dropna(subset=["best_lap_time"]).sort_values("created_at")
    fig.add_trace(
        go.Scatter(
            x=s["created_at"],
            y=s["best_lap_time"],
            mode="lines+markers",
            line=dict(color="#38bdf8", width=2),
            marker=dict(size=8),
            name="Session best",
            customdata=s["id"],
            hovertemplate="Session #%{customdata}<br>%{y:.3f}s<extra></extra>",
        )
    )
    fig.update_layout(**DARK_LAYOUT, title="Best lap per session", height=340, yaxis_title="Lap time (s)")
    return fig


def gg_diagram(lap_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if lap_df.empty or "g_lat" not in lap_df.columns or "g_long" not in lap_df.columns:
        fig.update_layout(**DARK_LAYOUT, title="G-G diagram", height=420)
        return fig
    fig.add_trace(
        go.Scatter(
            x=lap_df["g_lat"],
            y=lap_df["g_long"],
            mode="markers",
            marker=dict(
                size=3,
                color=lap_df["speed"] if "speed" in lap_df.columns else "#38bdf8",
                colorscale="Turbo",
                showscale=True,
                colorbar=dict(title="km/h"),
            ),
            name="G-G",
        )
    )
    fig.add_vline(x=0, line_color="#6b7280", line_width=1)
    fig.add_hline(y=0, line_color="#6b7280", line_width=1)
    fig.update_layout(
        **DARK_LAYOUT,
        title="Traction circle (G-G)",
        height=440,
        xaxis_title="Lateral G",
        yaxis_title="Longitudinal G",
        yaxis=dict(scaleanchor="x", scaleratio=1),
    )
    return fig


def tyre_temps_plot(lap_df: pd.DataFrame) -> go.Figure:
    x, x_title = _x_axis(lap_df)
    fig = go.Figure()
    colors = {"RL": "#60a5fa", "RR": "#a78bfa", "FL": "#34d399", "FR": "#fbbf24"}
    for i, lab in enumerate(["RL", "RR", "FL", "FR"]):
        col = f"tyre_temp_{i}"
        if col in lap_df.columns:
            fig.add_trace(go.Scatter(x=x, y=lap_df[col], name=lab, line=dict(color=colors[lab], width=2)))
    fig.update_layout(**DARK_LAYOUT, title="Tyre surface temps", height=360, xaxis_title=x_title, yaxis_title="°C")
    return fig


def tyre_wear_bars(lap_df: pd.DataFrame) -> go.Figure:
    labels, values = [], []
    for i, lab in enumerate(["RL", "RR", "FL", "FR"]):
        col = f"tyre_wear_{i}"
        if col in lap_df.columns:
            labels.append(lab)
            values.append(float(lap_df[col].iloc[-1]) * 100)
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=["#60a5fa", "#a78bfa", "#34d399", "#fbbf24"]))
    fig.update_layout(**DARK_LAYOUT, title="Tyre wear at end of lap (%)", height=320, yaxis_title="%")
    return fig


def ers_plot(lap_df: pd.DataFrame) -> go.Figure:
    from .ers import enrich_ers

    lap = enrich_ers(lap_df)
    x, x_title = _x_axis(lap)
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=("ERS store (MJ)", "Deploy mode", "Clipped Δ store (harvest +, deploy −)"),
        row_heights=[0.4, 0.25, 0.35],
    )
    if "ers_store_mj" in lap.columns:
        fig.add_trace(
            go.Scatter(x=x, y=lap["ers_store_mj"], name="Store (MJ)", line=dict(color="#c084fc", width=2)),
            row=1,
            col=1,
        )
    if "ers_deployMode" in lap.columns:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=lap["ers_deployMode"],
                name="Mode",
                line=dict(color="#f472b6", width=2, shape="vh"),
            ),
            row=2,
            col=1,
        )
    if "ers_dstore" in lap.columns:
        colors = np.where(lap["ers_dstore"] >= 0, "#34d399", "#f87171")
        fig.add_trace(
            go.Bar(x=x, y=lap["ers_dstore"], name="Δ MJ", marker_color=colors, showlegend=False),
            row=3,
            col=1,
        )
    fig.update_layout(**DARK_LAYOUT, height=560, title="ERS trace", hovermode="x unified")
    fig.update_xaxes(title_text=x_title, row=3, col=1)
    return fig


def ers_session_scatter(table: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if table.empty:
        fig.update_layout(**DARK_LAYOUT, title="Practice: pace vs starting SOC", height=360)
        return fig
    fig.add_trace(
        go.Scatter(
            x=table["start_mj"],
            y=table["lap_time"],
            mode="markers+text",
            text=[f"L{int(l)}" for l in table["lap"]],
            textposition="top center",
            marker=dict(
                size=12,
                color=table["deployed_mj"],
                colorscale="Plasma",
                showscale=True,
                colorbar=dict(title="Deployed MJ"),
            ),
            customdata=np.column_stack(
                [table["end_mj"], table["deployed_mj"], table["harvested_mj"]]
            ),
            hovertemplate=(
                "Lap start %{x:.2f} MJ<br>Lap time %{y:.3f}s<br>"
                "End %{customdata[0]:.2f} · Dep %{customdata[1]:.2f} · Harv %{customdata[2]:.2f}"
                "<extra></extra>"
            ),
            name="Laps",
        )
    )
    fig.update_layout(
        **DARK_LAYOUT,
        title="Practice map: starting battery vs lap time",
        height=380,
        xaxis_title="Start SOC (MJ)",
        yaxis_title="Lap time (s)",
    )
    return fig


def ers_profile_bars(profile: pd.DataFrame, title: str = "Deploy / harvest along lap") -> go.Figure:
    fig = go.Figure()
    if profile.empty:
        fig.update_layout(**DARK_LAYOUT, title=title, height=360)
        return fig
    fig.add_trace(
        go.Bar(
            x=profile["dist_mid"],
            y=profile["deployed_mj"],
            name="Deployed",
            marker_color="#f87171",
        )
    )
    fig.add_trace(
        go.Bar(
            x=profile["dist_mid"],
            y=profile["harvested_mj"],
            name="Harvested",
            marker_color="#34d399",
        )
    )
    fig.update_layout(
        **DARK_LAYOUT,
        title=title,
        height=380,
        barmode="group",
        xaxis_title="Distance (m)",
        yaxis_title="MJ",
    )
    return fig


def ers_advice_map(advice: pd.DataFrame, outline_lap: pd.DataFrame | None = None) -> go.Figure:
    """Colour track distance bins by DEPLOY / HARVEST / HOLD recommendation."""
    fig = go.Figure()
    if advice.empty:
        fig.update_layout(**DARK_LAYOUT, title="Recommended energy map", height=420)
        return fig

    color_map = {"DEPLOY": "#f43f5e", "HARVEST": "#22c55e", "HOLD": "#94a3b8"}
    if (
        outline_lap is not None
        and not outline_lap.empty
        and "pos_x" in outline_lap.columns
        and "pos_y" in outline_lap.columns
        and "lap_distance" in outline_lap.columns
    ):
        lap = outline_lap.sort_values("lap_distance")
        labels = []
        colors = []
        for d in lap["lap_distance"]:
            row = advice.iloc[(advice["dist_mid"] - d).abs().argmin()]
            labels.append(row["advice"])
            colors.append(color_map.get(row["advice"], "#94a3b8"))
        fig.add_trace(
            go.Scatter(
                x=lap["pos_x"],
                y=lap["pos_y"],
                mode="markers",
                marker=dict(size=5, color=colors),
                text=labels,
                hovertemplate="%{text}<br>%{x:.0f}, %{y:.0f}<extra></extra>",
                name="Advice",
            )
        )
        fig.update_layout(
            **DARK_LAYOUT,
            title="Practice-derived energy map (DEPLOY / HARVEST / HOLD)",
            height=480,
            xaxis=dict(scaleanchor="y", scaleratio=1, showgrid=False, zeroline=False, showticklabels=False, title=""),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
        )
    else:
        fig.add_trace(
            go.Bar(
                x=[f"{a:.0f}" for a in advice["dist_mid"]],
                y=advice["spend_score"],
                marker_color=[color_map.get(a, "#94a3b8") for a in advice["advice"]],
                text=advice["advice"],
                textposition="outside",
            )
        )
        fig.update_layout(**DARK_LAYOUT, title="Energy advice by distance", height=380, xaxis_title="Dist mid (m)")
    return fig


def ers_corner_bars(corner_ers: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if corner_ers.empty:
        fig.update_layout(**DARK_LAYOUT, title="ERS by corner", height=360)
        return fig
    fig.add_trace(go.Bar(x=corner_ers["corner_id"], y=corner_ers["deployed_mj"], name="Deploy", marker_color="#f87171"))
    fig.add_trace(go.Bar(x=corner_ers["corner_id"], y=corner_ers["harvested_mj"], name="Harvest", marker_color="#34d399"))
    fig.update_layout(**DARK_LAYOUT, title="ERS by corner / segment", height=380, barmode="group", yaxis_title="MJ")
    return fig


def sector_bar(sectors: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if sectors.empty:
        return fig
    colors = ["#22c55e" if v < 0 else "#ef4444" for v in sectors["delta_s"]]
    fig.add_trace(
        go.Bar(
            x=[f"S{s}" for s in sectors["sector"]],
            y=sectors["delta_s"],
            marker_color=colors,
            text=[f"{v:+.3f}" for v in sectors["delta_s"]],
            textposition="outside",
        )
    )
    fig.update_layout(**DARK_LAYOUT, title="Sector delta (cmp − ref), negative = faster", height=320, yaxis_title="Δs")
    return fig


def fuel_tyre_stint(summary: pd.DataFrame) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if summary.empty:
        return fig
    if "fuel_end" in summary.columns:
        fig.add_trace(
            go.Scatter(x=summary["lap"], y=summary["fuel_end"], name="Fuel", line=dict(color="#38bdf8")),
            secondary_y=False,
        )
    if "tyre_wear_avg" in summary.columns:
        fig.add_trace(
            go.Scatter(x=summary["lap"], y=summary["tyre_wear_avg"], name="Tyre wear %", line=dict(color="#f97316")),
            secondary_y=True,
        )
    fig.update_layout(**DARK_LAYOUT, title="Stint: fuel & tyre wear", height=340)
    fig.update_yaxes(title_text="Fuel", secondary_y=False)
    fig.update_yaxes(title_text="Wear %", secondary_y=True)
    return fig


def setup_delta_bars(est_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if est_df.empty or "Est. Δt (s)" not in est_df.columns:
        fig.update_layout(**DARK_LAYOUT, title="Setup Δt by parameter", height=360)
        return fig
    colors = ["#22c55e" if v < 0 else "#ef4444" for v in est_df["Est. Δt (s)"]]
    fig.add_trace(
        go.Bar(
            x=est_df["Parameter"],
            y=est_df["Est. Δt (s)"],
            marker_color=colors,
            text=[f"{v:+.3f}" for v in est_df["Est. Δt (s)"]],
            textposition="outside",
        )
    )
    fig.update_layout(
        **DARK_LAYOUT,
        title="Estimated lap-time effect by change (negative = faster)",
        height=400,
        yaxis_title="Δt (s)",
    )
    return fig


def setup_breakdown_pie(breakdown: dict) -> go.Figure:
    fig = go.Figure()
    items = [(k, v) for k, v in breakdown.items() if abs(v) > 1e-4]
    if not items:
        fig.update_layout(**DARK_LAYOUT, title="Δt breakdown", height=320)
        return fig
    fig.add_trace(
        go.Bar(
            x=[k for k, _ in items],
            y=[v for _, v in items],
            marker_color=["#22c55e" if v < 0 else "#f87171" for _, v in items],
            text=[f"{v:+.3f}" for _, v in items],
            textposition="outside",
        )
    )
    fig.update_layout(**DARK_LAYOUT, title="Δt by category", height=320, yaxis_title="s")
    return fig


def stint_efficiency_chart(table: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if table.empty:
        fig.update_layout(**DARK_LAYOUT, title="Stint efficiency", height=360)
        return fig
    fig.add_trace(
        go.Scatter(
            x=table["fuel_used"],
            y=table["lap_time"],
            mode="markers+text",
            text=[f"L{int(l)}" for l in table["lap"]],
            textposition="top center",
            marker=dict(
                size=12,
                color=table["stint_score"] if "stint_score" in table.columns else "#38bdf8",
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title="Score"),
            ),
            hovertemplate="Fuel %{x:.2f}<br>Time %{y:.3f}s<extra></extra>",
        )
    )
    fig.update_layout(
        **DARK_LAYOUT,
        title="Fuel vs lap time (higher score = better management)",
        height=380,
        xaxis_title="Fuel used",
        yaxis_title="Lap time (s)",
    )
    return fig


def active_aero_plot(lap_df: pd.DataFrame) -> go.Figure:
    """Active aero mode vs distance, with optional speed overlay."""
    from .ers import enrich_2026_channels

    lap = enrich_2026_channels(lap_df)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if lap.empty or "activeAero_mode" not in lap.columns:
        fig.update_layout(**DARK_LAYOUT, title="Active aero", height=360)
        return fig
    x, x_title = _x_axis(lap)
    fig.add_trace(
        go.Scatter(
            x=x,
            y=lap["activeAero_mode"],
            name="Aero mode",
            line=dict(color="#38bdf8", width=2, shape="vh"),
        ),
        secondary_y=False,
    )
    if "speed" in lap.columns:
        fig.add_trace(
            go.Scatter(x=x, y=lap["speed"], name="Speed", line=dict(color="#94a3b8", width=1), opacity=0.7),
            secondary_y=True,
        )
    fig.update_layout(**DARK_LAYOUT, title="Active aero vs distance (1 = low drag)", height=360, hovermode="x unified")
    fig.update_xaxes(title_text=x_title)
    fig.update_yaxes(title_text="Mode", secondary_y=False, dtick=1)
    fig.update_yaxes(title_text="Speed", secondary_y=True, showgrid=False)
    return fig


def active_aero_profile_bars(profile: pd.DataFrame, ref_profile: pd.DataFrame | None = None) -> go.Figure:
    fig = go.Figure()
    if profile.empty:
        fig.update_layout(**DARK_LAYOUT, title="Low-drag aero by distance", height=360)
        return fig
    fig.add_trace(
        go.Bar(
            x=profile["dist_mid"],
            y=profile["low_drag_pct"],
            name="Focus low-drag %",
            marker_color="#38bdf8",
        )
    )
    if ref_profile is not None and not ref_profile.empty:
        fig.add_trace(
            go.Bar(
                x=ref_profile["dist_mid"],
                y=ref_profile["low_drag_pct"],
                name="Ref low-drag %",
                marker_color="#64748b",
            )
        )
    fig.update_layout(
        **DARK_LAYOUT,
        title="Active aero: % of bin in low-drag",
        height=360,
        barmode="group",
        xaxis_title="Distance (m)",
        yaxis_title="% low drag",
    )
    return fig


def power_split_plot(profile: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if profile.empty:
        fig.update_layout(**DARK_LAYOUT, title="ICE vs MGUK power", height=380)
        return fig
    fig.add_trace(
        go.Bar(x=profile["dist_mid"], y=profile["ice_kw"], name="ICE (kW)", marker_color="#fbbf24")
    )
    fig.add_trace(
        go.Bar(x=profile["dist_mid"], y=profile["mguk_kw"], name="MGUK (kW)", marker_color="#c084fc")
    )
    fig.update_layout(
        **DARK_LAYOUT,
        title="ICE vs MGUK power along lap",
        height=380,
        barmode="stack",
        xaxis_title="Distance (m)",
        yaxis_title="kW (avg)",
    )
    return fig


def overtake_soc_plot(lap_df: pd.DataFrame) -> go.Figure:
    from .ers import overtake_timeline

    tl = overtake_timeline(lap_df)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.45, 0.55])
    if tl.empty:
        fig.update_layout(**DARK_LAYOUT, title="Overtake / SOC", height=400)
        return fig
    x = tl["lap_distance"]
    if "ot_allowed" in tl.columns:
        fig.add_trace(
            go.Scatter(x=x, y=tl["ot_allowed"], name="Allowed", line=dict(color="#94a3b8", shape="vh")),
            row=1,
            col=1,
        )
    if "ot_active" in tl.columns:
        fig.add_trace(
            go.Scatter(x=x, y=tl["ot_active"], name="Used", line=dict(color="#f472b6", shape="vh", width=2)),
            row=1,
            col=1,
        )
    if "ers_store_mj" in tl.columns:
        fig.add_trace(
            go.Scatter(x=x, y=tl["ers_store_mj"], name="SOC (MJ)", line=dict(color="#c084fc", width=2)),
            row=2,
            col=1,
        )
    fig.update_layout(**DARK_LAYOUT, title="Overtake available / used + SOC", height=420, hovermode="x unified")
    fig.update_xaxes(title_text="Distance (m)", row=2, col=1)
    fig.update_yaxes(title_text="Flag", row=1, col=1, range=[-0.05, 1.05])
    fig.update_yaxes(title_text="MJ", row=2, col=1)
    return fig


def fuel_window_plot(summary: pd.DataFrame, projection: pd.DataFrame, fuel_window=None) -> go.Figure:
    fig = go.Figure()
    if not summary.empty and "fuel_end" in summary.columns:
        fig.add_trace(
            go.Scatter(
                x=summary["lap"],
                y=summary["fuel_end"],
                name="Fuel (actual)",
                mode="lines+markers",
                line=dict(color="#38bdf8", width=2),
            )
        )
    if projection is not None and not projection.empty and projection["fuel_proj"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=projection["lap"],
                y=projection["fuel_proj"],
                name="Fuel (projected)",
                mode="lines",
                line=dict(color="#38bdf8", width=2, dash="dash"),
            )
        )
    if fuel_window is not None and getattr(fuel_window, "target_laps", None) is not None:
        fig.add_vline(
            x=fuel_window.target_laps - 1,
            line_dash="dot",
            line_color="#fbbf24",
            annotation_text="Target",
        )
    fig.add_hline(y=0, line_dash="dot", line_color="#f87171")
    fig.update_layout(**DARK_LAYOUT, title="Fuel remaining window", height=360, xaxis_title="Lap", yaxis_title="Fuel")
    return fig


def tyre_cliff_plot(summary: pd.DataFrame, projection: pd.DataFrame, tyre_cliff=None) -> go.Figure:
    fig = go.Figure()
    if not summary.empty and "tyre_wear_avg" in summary.columns:
        wear = summary["tyre_wear_avg"].where(summary["tyre_wear_avg"] >= 0)
        fig.add_trace(
            go.Scatter(
                x=summary["lap"],
                y=wear,
                name="Wear % (actual)",
                mode="lines+markers",
                line=dict(color="#f97316", width=2),
            )
        )
    if projection is not None and not projection.empty and projection["wear_proj_pct"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=projection["lap"],
                y=projection["wear_proj_pct"],
                name="Wear % (projected)",
                mode="lines",
                line=dict(color="#f97316", width=2, dash="dash"),
            )
        )
    cliff = getattr(tyre_cliff, "cliff_wear_pct", 55.0) if tyre_cliff is not None else 55.0
    fig.add_hline(y=cliff, line_dash="dot", line_color="#ef4444", annotation_text=f"Cliff {cliff:.0f}%")
    fig.update_layout(**DARK_LAYOUT, title="Tyre wear cliff projection", height=360, xaxis_title="Lap", yaxis_title="Wear %")
    return fig
