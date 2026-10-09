"""F1 2026 ERS / energy deployment analysis and coaching."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .corners import analyze_lap_corners, resolve_corners
from .framecache import per_frame
from .metrics import build_lap_summary, get_lap

# Heuristic labels for SRT ers_deployMode values observed in F1 26 dumps.
# Mode 3 correlates with full-throttle / higher speed; mode 1 with mixed/harvest.
DEPLOY_MODE_LABELS: dict[int, str] = {
    0: "Off / None",
    1: "Harvest / Balanced",
    2: "Qualify / Hotlap",
    3: "Deploy / Overtake",
}

# Ignore single-sample store jumps (flashback, packet glitch, unit blip).
MAX_SAMPLE_DELTA_MJ = 0.05


@dataclass
class ErsTip:
    severity: str  # info | tip | warning
    title: str
    detail: str


def enrich_ers(lap_df: pd.DataFrame) -> pd.DataFrame:
    """Add clipped battery deltas and deploy/harvest flags."""
    out = lap_df.sort_values("lap_distance").copy() if "lap_distance" in lap_df.columns else lap_df.copy()
    if "ers_store_mj" not in out.columns:
        if "ers_store" in out.columns:
            store = out["ers_store"].astype(float)
            out["ers_store_mj"] = np.where(store > 1000, store / 1e6, store)
        else:
            return out

    store = out["ers_store_mj"].astype(float)
    # F1-scale battery; reject absurd spikes before smoothing
    store = store.clip(lower=0.0, upper=15.0)
    out["ers_store_mj"] = store
    if len(store) >= 9:
        smooth = store.rolling(9, center=True, min_periods=1).median()
    else:
        smooth = store
    raw = smooth.diff().fillna(0.0)
    # Hard reject flashback / teleport spikes
    clipped = raw.where(raw.abs() <= MAX_SAMPLE_DELTA_MJ, 0.0)
    out["ers_store_smooth"] = smooth
    out["ers_dstore"] = clipped
    out["ers_dstore_raw"] = store.diff().fillna(0.0)
    out["deploying"] = clipped < -0.0002
    out["harvesting"] = clipped > 0.0002

    if "ers_deployMode" in out.columns:
        mode = out["ers_deployMode"].fillna(-1).astype(int)
        out["ers_mode_label"] = mode.map(lambda m: DEPLOY_MODE_LABELS.get(m, f"Mode {m}"))
        out["in_deploy_mode"] = mode == int(mode.max()) if mode.max() >= 2 else mode >= 3
    else:
        out["in_deploy_mode"] = out["deploying"]

    if "throttle" in out.columns:
        out["wot"] = out["throttle"] > 0.95
        # Wasteful: battery falling while not flat-out (and not clearly braking harvest)
        braking = out["brake"] > 0.15 if "brake" in out.columns else False
        out["deploy_on_partial"] = out["deploying"] & (out["throttle"] < 0.85) & (~braking)
        out["harvest_on_wot"] = out["harvesting"] & out["wot"]
    else:
        out["wot"] = False
        out["deploy_on_partial"] = False
        out["harvest_on_wot"] = False

    return out


def lap_ers_summary(lap_df: pd.DataFrame) -> dict:
    """Scalar ERS KPIs for one lap."""
    lap = enrich_ers(lap_df)
    if "ers_store_mj" not in lap.columns or lap.empty:
        return {}

    store = lap["ers_store_mj"].astype(float)
    smooth = lap["ers_store_smooth"] if "ers_store_smooth" in lap.columns else store
    start = float(store.iloc[0])
    end = float(store.iloc[-1])
    minimum = float(smooth.min())
    maximum = float(smooth.max())
    # Net SOC path on smoothed battery (much less noise than raw sample sums)
    ds = smooth.diff().fillna(0.0)
    harvested = float(ds.clip(lower=0).sum())
    deployed = float((-ds.clip(upper=0)).sum())
    deployed = float(min(deployed, max(0.0, start - minimum) + 1e-9))
    harvested = float(min(harvested, max(0.0, maximum - minimum) + 1e-9))

    out = {
        "start_mj": start,
        "end_mj": end,
        "net_mj": end - start,
        "min_mj": minimum,
        "max_mj": maximum,
        "soc_swing_mj": maximum - minimum,
        "deployed_mj": max(0.0, deployed),
        "harvested_mj": max(0.0, harvested),
        "empty_pct": float((store < 0.05).mean() * 100),
        "deploy_mode_pct": float(lap["in_deploy_mode"].mean() * 100) if "in_deploy_mode" in lap else 0.0,
        "partial_throttle_deploy_pct": float(lap["deploy_on_partial"].mean() * 100),
        "wot_pct": float(lap["wot"].mean() * 100) if "wot" in lap else 0.0,
    }
    if "drs" in lap.columns:
        out["drs_pct"] = float((lap["drs"] > 0).mean() * 100)
        out["deploy_with_drs_pct"] = float(((lap["in_deploy_mode"]) & (lap["drs"] > 0)).mean() * 100)
    return out


@per_frame()
def session_ers_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per valid lap with pace + ERS KPIs (practice gold)."""
    summary = build_lap_summary(df)
    if summary.empty:
        return pd.DataFrame()

    rows = []
    for _, row in summary.iterrows():
        lap = get_lap(df, int(row["lap"]))
        kpis = lap_ers_summary(lap)
        if not kpis:
            continue
        rows.append(
            {
                "lap": int(row["lap"]),
                "lap_time": float(row["lap_time"]),
                "delta_best": float(row.get("delta_best") or 0),
                "is_best": bool(row.get("is_best")),
                **kpis,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out

    # Efficiency: lap time vs energy spent (lower time with less dump is better for race;
    # for quali, time rules). Practice score blends pace and leftover battery.
    best_t = out["lap_time"].min()
    out["pace_score"] = (best_t / out["lap_time"]).clip(0, 1) * 100
    # Prefer ending with some store for race sims; for pure push laps ending empty can be OK
    out["exit_soc"] = (out["end_mj"] / out["max_mj"].replace(0, np.nan).fillna(1)).clip(0, 1) * 100
    out["ers_discipline"] = (
        100
        - out["partial_throttle_deploy_pct"] * 2
        - (out["empty_pct"] * 0.15)
    ).clip(0, 100)
    return out


def ers_by_distance(lap_df: pd.DataFrame, n_bins: int = 24) -> pd.DataFrame:
    """Profile deploy/harvest along the lap using net smoothed SOC per bin."""
    lap = enrich_ers(lap_df)
    if lap.empty or "lap_distance" not in lap.columns or "ers_store_smooth" not in lap.columns:
        return pd.DataFrame()

    length = float(lap["lap_distance"].max())
    edges = np.linspace(0, length, n_bins + 1)
    rows = []
    for i in range(n_bins):
        mask = (lap["lap_distance"] >= edges[i]) & (
            lap["lap_distance"] <= edges[i + 1] if i == n_bins - 1 else lap["lap_distance"] < edges[i + 1]
        )
        chunk = lap.loc[mask]
        if chunk.empty:
            continue
        net = float(chunk["ers_store_smooth"].iloc[-1] - chunk["ers_store_smooth"].iloc[0])
        rows.append(
            {
                "bin": i + 1,
                "dist_start": float(edges[i]),
                "dist_end": float(edges[i + 1]),
                "dist_mid": float((edges[i] + edges[i + 1]) / 2),
                "deployed_mj": float(max(0.0, -net)),
                "harvested_mj": float(max(0.0, net)),
                "net_mj": net,
                "store_avg": float(chunk["ers_store_mj"].mean()),
                "deploy_mode_pct": float(chunk["in_deploy_mode"].mean() * 100),
                "throttle_avg": float(chunk["throttle"].mean()) if "throttle" in chunk else np.nan,
                "speed_avg": float(chunk["speed"].mean()) if "speed" in chunk else np.nan,
                "drs_pct": float((chunk["drs"] > 0).mean() * 100) if "drs" in chunk else np.nan,
            }
        )
    return pd.DataFrame(rows)


def ers_by_corner(
    lap_df: pd.DataFrame,
    track: str | None,
    track_length: float | None = None,
) -> pd.DataFrame:
    lap = enrich_ers(lap_df)
    corners = resolve_corners(track, track_length, lap)
    if not corners or "ers_store_smooth" not in lap.columns:
        return pd.DataFrame()

    rows = []
    for c in corners:
        mask = (lap["lap_distance"] >= c.start) & (lap["lap_distance"] < c.end)
        chunk = lap.loc[mask]
        if chunk.empty:
            continue
        net = float(chunk["ers_store_smooth"].iloc[-1] - chunk["ers_store_smooth"].iloc[0])
        rows.append(
            {
                "corner_id": c.id,
                "corner_name": c.name,
                "kind": c.kind,
                "deployed_mj": float(max(0.0, -net)),
                "harvested_mj": float(max(0.0, net)),
                "net_mj": net,
                "deploy_mode_pct": float(chunk["in_deploy_mode"].mean() * 100),
                "throttle_avg": float(chunk["throttle"].mean()) if "throttle" in chunk else np.nan,
                "vmin": float(chunk["speed"].min()) if "speed" in chunk else np.nan,
            }
        )
    return pd.DataFrame(rows)


def compare_ers_profiles(focus: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """Align distance bins: positive deploy_delta => focus deployed more than ref."""
    if focus.empty or reference.empty:
        return pd.DataFrame()
    merged = focus.merge(
        reference[["bin", "deployed_mj", "harvested_mj", "deploy_mode_pct"]].rename(
            columns={
                "deployed_mj": "ref_deployed_mj",
                "harvested_mj": "ref_harvested_mj",
                "deploy_mode_pct": "ref_deploy_mode_pct",
            }
        ),
        on="bin",
        how="left",
    )
    merged["deploy_delta"] = merged["deployed_mj"] - merged["ref_deployed_mj"]
    merged["harvest_delta"] = merged["harvested_mj"] - merged["ref_harvested_mj"]
    return merged


def practice_ers_insights(
    df: pd.DataFrame,
    focus_lap: int,
    reference_lap: int | None = None,
    track: str | None = None,
    track_length: float | None = None,
) -> list[ErsTip]:
    """
    Coaching from practice runs: how energy use related to pace, and where to
    put deploy for 2026-style ERS dependence.
    """
    tips: list[ErsTip] = []
    table = session_ers_table(df)
    if table.empty:
        return [ErsTip("warning", "No ERS data", "This session has no battery / deploy channels.",)]

    focus_rows = table[table["lap"] == focus_lap]
    if focus_rows.empty:
        return [ErsTip("warning", "Lap missing", f"Lap {focus_lap} not in ERS table.")]
    focus = focus_rows.iloc[0]
    best = table.loc[table["is_best"]].iloc[0]
    ref_lap = reference_lap if reference_lap is not None else int(best["lap"])
    ref_rows = table[table["lap"] == ref_lap]
    ref = ref_rows.iloc[0] if not ref_rows.empty else best

    tips.append(
        ErsTip(
            "info",
            "Battery window",
            f"Lap {focus_lap}: {focus['start_mj']:.2f} → {focus['end_mj']:.2f} MJ "
            f"(deployed ~{focus['deployed_mj']:.2f}, harvested ~{focus['harvested_mj']:.2f}).",
        )
    )

    # Practice correlation: did battery help pace?
    charged = table[table["start_mj"] >= 0.4]
    empty = table[table["start_mj"] < 0.15]
    if len(charged) >= 2 and len(empty) >= 2:
        charged_best = float(charged["lap_time"].min())
        empty_best = float(empty["lap_time"].min())
        gap = empty_best - charged_best
        if gap > 0.15:
            tips.append(
                ErsTip(
                    "tip",
                    "Battery buys lap time",
                    f"In this practice, best charged lap is {charged_best:.3f}s vs best low-SOC "
                    f"{empty_best:.3f}s ({gap:.3f}s). Build a harvest lap, then a push lap.",
                )
            )
        elif gap < -0.15:
            tips.append(
                ErsTip(
                    "info",
                    "Pace not SOC-limited",
                    f"Your fastest work came with low battery ({empty_best:.3f}s vs charged {charged_best:.3f}s). "
                    "Focus on deploy placement and lift-coast harvest, not just filling the store.",
                )
            )

    if focus["partial_throttle_deploy_pct"] > 1.5:
        tips.append(
            ErsTip(
                "warning",
                "Deploying off full throttle",
                f"~{focus['partial_throttle_deploy_pct']:.1f}% of samples dump energy below 85% throttle. "
                "In 2026 regs that wastes battery — deploy on exits / straights when you're flat.",
            )
        )

    if focus["empty_pct"] > 35 and focus["lap_time"] > best["lap_time"] + 0.3:
        tips.append(
            ErsTip(
                "tip",
                "Running empty while off-pace",
                f"Battery was near empty for {focus['empty_pct']:.0f}% of the lap and you were "
                f"+{focus['lap_time'] - best['lap_time']:.3f}s off best. Shorten mid-lap deploy bursts; "
                "save a hit for the longest straight.",
            )
        )

    if focus["end_mj"] < 0.05 and focus["start_mj"] > 0.8:
        tips.append(
            ErsTip(
                "info",
                "Full push discharge",
                "You started charged and finished empty — fine for a quali-style push. "
                "For race sims, target ending a push lap with ~10–20% store for the next one.",
            )
        )

    # Distance profile tips vs reference
    focus_lap_df = enrich_ers(get_lap(df, focus_lap))
    ref_lap_df = enrich_ers(get_lap(df, int(ref["lap"])))
    focus_prof = ers_by_distance(focus_lap_df, n_bins=12)
    ref_prof = ers_by_distance(ref_lap_df, n_bins=12)
    cmp = compare_ers_profiles(focus_prof, ref_prof)
    if not cmp.empty and cmp["deploy_delta"].notna().any():
        # Where reference deploys more on high-throttle zones
        over = cmp.sort_values("deploy_delta", ascending=False).iloc[0]
        under = cmp.sort_values("deploy_delta", ascending=True).iloc[0]
        if over["deploy_delta"] > 0.15:
            tips.append(
                ErsTip(
                    "tip",
                    "Heavier deploy than reference",
                    f"Around {over['dist_start']:.0f}–{over['dist_end']:.0f} m you spent "
                    f"+{over['deploy_delta']:.2f} MJ more than lap {int(ref['lap'])}. "
                    "Check if that zone is a straight/exit; if it's a mid-corner, pull deploy back.",
                )
            )
        if under["deploy_delta"] < -0.15:
            tips.append(
                ErsTip(
                    "tip",
                    "Missed deploy zone",
                    f"Around {under['dist_start']:.0f}–{under['dist_end']:.0f} m you deployed "
                    f"{abs(under['deploy_delta']):.2f} MJ less than lap {int(ref['lap'])}. "
                    "If throttle is flat there, add a short deploy pulse — high ROI in 2026.",
                )
            )

    # Corner-level: deploy on slow corners is bad; harvest under braking good
    corner_ers = ers_by_corner(focus_lap_df, track, track_length)
    if not corner_ers.empty:
        slow = corner_ers[(corner_ers["kind"] == "corner") & (corner_ers["vmin"] < 120)]
        if not slow.empty:
            worst = slow.sort_values("deployed_mj", ascending=False).iloc[0]
            if worst["deployed_mj"] > 0.25 and worst["throttle_avg"] < 0.7:
                tips.append(
                    ErsTip(
                        "warning",
                        f"Energy burned in {worst['corner_name']}",
                        f"~{worst['deployed_mj']:.2f} MJ deployed while average throttle was "
                        f"{worst['throttle_avg']:.0%}. Prefer harvest through the apex, deploy on exit.",
                    )
                )
        straights = corner_ers[corner_ers["kind"] == "straight"]
        if not straights.empty:
            top = straights.sort_values("deployed_mj", ascending=False).iloc[0]
            tips.append(
                ErsTip(
                    "info",
                    "Straight-line energy",
                    f"Biggest straight deploy: {top['corner_name']} (~{top['deployed_mj']:.2f} MJ, "
                    f"mode {top['deploy_mode_pct']:.0f}% of the segment).",
                )
            )

    # Reference practice recipe
    if len(table) >= 3:
        # Find a "build" lap: high harvest / end store, and a "push" lap: fast with deploy
        build = table.sort_values(["end_mj", "harvested_mj"], ascending=False).iloc[0]
        push = table.sort_values("lap_time").iloc[0]
        tips.append(
            ErsTip(
                "tip",
                "Practice recipe from this session",
                f"Use a build pattern like lap {int(build['lap'])} "
                f"(ended {build['end_mj']:.2f} MJ), then a push like lap {int(push['lap'])} "
                f"({push['lap_time']:.3f}s). Repeat: harvest → attack → brief cool.",
            )
        )

    # DRS synergy
    if focus.get("drs_pct", 0) > 5 and focus.get("deploy_with_drs_pct", 0) < 1:
        tips.append(
            ErsTip(
                "tip",
                "DRS without deploy",
                "DRS is open but little battery is dumped with it. Stack deploy + DRS on detection zones "
                "for maximum straight-line gain under 2026 powertrains.",
            )
        )

    return tips


def session_ers_insights(
    df: pd.DataFrame,
    *,
    track: str | None = None,
    track_length: float | None = None,
) -> list[ErsTip]:
    """Session-level ERS patterns — harvest/push recipe and SOC vs pace."""
    tips: list[ErsTip] = []
    table = session_ers_table(df)
    if table.empty:
        return [ErsTip("warning", "No ERS data", "This session has no battery / deploy channels.")]

    best = table.loc[table["is_best"]].iloc[0]

    charged = table[table["start_mj"] >= 0.4]
    empty = table[table["start_mj"] < 0.15]
    if len(charged) >= 2 and len(empty) >= 2:
        charged_best = float(charged["lap_time"].min())
        empty_best = float(empty["lap_time"].min())
        gap = empty_best - charged_best
        if gap > 0.15:
            tips.append(
                ErsTip(
                    "tip",
                    "Battery buys lap time",
                    f"Across this session, best charged lap is {charged_best:.3f}s vs best low-SOC "
                    f"{empty_best:.3f}s ({gap:.3f}s). Plan harvest laps before push laps.",
                )
            )
        elif gap < -0.15:
            tips.append(
                ErsTip(
                    "info",
                    "Pace not SOC-limited",
                    f"Fastest work often came with lower battery ({empty_best:.3f}s vs charged {charged_best:.3f}s). "
                    "Focus deploy placement and lift-coast harvest, not just filling the store.",
                )
            )

    if len(table) >= 3:
        build = table.sort_values(["end_mj", "harvested_mj"], ascending=False).iloc[0]
        push = table.sort_values("lap_time").iloc[0]
        tips.append(
            ErsTip(
                "tip",
                "Session ERS recipe",
                f"Pattern from this run: build like L{int(build['lap'])} "
                f"(ended {build['end_mj']:.2f} MJ), push like L{int(push['lap'])} "
                f"({push['lap_time']:.3f}s). Repeat harvest → attack.",
            )
        )

    if "partial_throttle_deploy_pct" in table.columns:
        partial = table[table["partial_throttle_deploy_pct"] > 1.5]
    else:
        partial = pd.DataFrame()
    if len(partial) >= max(2, len(table) // 3):
        tips.append(
            ErsTip(
                "warning",
                "Deploying off throttle (session)",
                f"{len(partial)}/{len(table)} laps dump significant energy below 85% throttle. "
                "Save deploy for straights and flat exits.",
            )
        )

    if "empty_pct" in table.columns:
        empty_heavy = table[(table["empty_pct"] > 35) & (table["lap_time"] > best["lap_time"] + 0.3)]
        if len(empty_heavy) >= max(2, len(table) // 4):
            tips.append(
                ErsTip(
                    "tip",
                    "Running empty while off-pace",
                    f"{len(empty_heavy)} laps ended near-empty without matching PB pace. "
                    "Shorten mid-lap deploy; save a hit for the longest straight.",
                )
            )

    return tips


def recommended_deploy_map(
    df: pd.DataFrame,
    track: str | None = None,
    track_length: float | None = None,
) -> pd.DataFrame:
    """
    From all practice laps, find distance bins where high deploy correlated
    with faster rolling pace (avg speed) — a simple 'where to spend' map.
    """
    summary = build_lap_summary(df)
    if summary.empty or len(summary) < 2:
        return pd.DataFrame()

    # Use top half of laps as "good" reference set
    cutoff = float(summary["lap_time"].quantile(0.5))
    good_laps = summary.loc[summary["lap_time"] <= cutoff, "lap"].astype(int).tolist()
    profiles = []
    for lap_n in good_laps:
        prof = ers_by_distance(get_lap(df, lap_n), n_bins=16)
        if not prof.empty:
            prof = prof.copy()
            prof["lap"] = lap_n
            profiles.append(prof)
    if not profiles:
        return pd.DataFrame()

    all_p = pd.concat(profiles, ignore_index=True)
    grouped = (
        all_p.groupby("bin", as_index=False)
        .agg(
            dist_start=("dist_start", "mean"),
            dist_end=("dist_end", "mean"),
            dist_mid=("dist_mid", "mean"),
            deploy_mj=("deployed_mj", "mean"),
            harvest_mj=("harvested_mj", "mean"),
            throttle_avg=("throttle_avg", "mean"),
            speed_avg=("speed_avg", "mean"),
            deploy_mode_pct=("deploy_mode_pct", "mean"),
        )
    )
    # Rank: prefer high deploy with high throttle (efficient spend)
    grouped["spend_score"] = (
        grouped["deploy_mode_pct"].fillna(0) / 100.0
    ) * (0.35 + 0.65 * grouped["throttle_avg"].fillna(0)) + 0.15 * grouped["deploy_mj"]
    grouped["priority"] = grouped["spend_score"].rank(ascending=False, method="dense").astype(int)
    grouped["advice"] = np.where(
        (grouped["deploy_mode_pct"] > 35) & (grouped["throttle_avg"] > 0.85),
        "DEPLOY",
        np.where(
            ((grouped["harvest_mj"] > grouped["deploy_mj"]) | (grouped["deploy_mode_pct"] < 15))
            & (grouped["throttle_avg"] < 0.7),
            "HARVEST",
            "HOLD",
        ),
    )
    return grouped.sort_values("priority")


# ---------------------------------------------------------------------------
# 2026 channels: active aero, overtake, ICE / MGUK power split
# ---------------------------------------------------------------------------

ACTIVE_AERO_LABELS: dict[int, str] = {
    0: "High downforce",
    1: "Low drag",
}


def enrich_2026_channels(lap_df: pd.DataFrame) -> pd.DataFrame:
    """Flags and normalised power columns for 2026 SRT channels."""
    out = lap_df.sort_values("lap_distance").copy() if "lap_distance" in lap_df.columns else lap_df.copy()

    if "activeAero_mode" in out.columns:
        mode = out["activeAero_mode"].fillna(0).astype(int)
        out["activeAero_mode"] = mode
        out["aero_low_drag"] = mode >= 1
        out["aero_mode_label"] = mode.map(lambda m: ACTIVE_AERO_LABELS.get(m, f"Mode {m}"))
    else:
        out["aero_low_drag"] = False

    if "overtake_allowed" in out.columns:
        out["ot_allowed"] = out["overtake_allowed"].fillna(0).astype(float) > 0.5
    else:
        out["ot_allowed"] = False

    if "overtake" in out.columns:
        # SRT dumps may hold the button as 0/1; treat >0.5 as pressed.
        out["ot_active"] = out["overtake"].fillna(0).astype(float) > 0.5
    else:
        out["ot_active"] = False

    out["ot_available_unused"] = out["ot_allowed"] & (~out["ot_active"])

    for src, dst in (("ice_power", "ice_kw"), ("mguk_power", "mguk_kw")):
        if src in out.columns:
            raw = out[src].astype(float)
            # Game values are typically Watts; fall back if already kW-scale.
            out[dst] = np.where(raw.abs().median() > 2000, raw / 1000.0, raw)
        elif dst not in out.columns:
            out[dst] = np.nan

    if "ice_kw" in out.columns and "mguk_kw" in out.columns:
        ice = out["ice_kw"].fillna(0.0)
        mguk = out["mguk_kw"].fillna(0.0)
        total = ice + mguk
        out["power_total_kw"] = total
        out["mguk_share"] = np.where(total > 1.0, mguk / total, np.nan)

    if "ers_store_mj" not in out.columns and "ers_store" in out.columns:
        store = out["ers_store"].astype(float)
        out["ers_store_mj"] = np.where(store > 1000, store / 1e6, store)

    return out


def lap_2026_summary(lap_df: pd.DataFrame) -> dict:
    """Scalar KPIs for active aero / overtake / ICE–MGUK on one lap."""
    lap = enrich_2026_channels(lap_df)
    if lap.empty:
        return {}

    out: dict = {}
    n = max(len(lap), 1)

    if "activeAero_mode" in lap.columns:
        low = float(lap["aero_low_drag"].mean() * 100)
        out["aero_low_drag_pct"] = low
        out["aero_high_df_pct"] = 100.0 - low
        if "speed" in lap.columns:
            out["aero_low_drag_speed"] = float(lap.loc[lap["aero_low_drag"], "speed"].mean()) if lap["aero_low_drag"].any() else np.nan
            out["aero_high_df_speed"] = float(lap.loc[~lap["aero_low_drag"], "speed"].mean()) if (~lap["aero_low_drag"]).any() else np.nan

    if "overtake" in lap.columns or "overtake_allowed" in lap.columns:
        allowed_pct = float(lap["ot_allowed"].mean() * 100)
        used_pct = float(lap["ot_active"].mean() * 100)
        out["overtake_allowed_pct"] = allowed_pct
        out["overtake_used_pct"] = used_pct
        out["overtake_unused_pct"] = float(lap["ot_available_unused"].mean() * 100)
        # Duty when available: used / allowed samples
        if lap["ot_allowed"].any():
            out["overtake_duty_when_allowed"] = float(lap.loc[lap["ot_allowed"], "ot_active"].mean() * 100)
        else:
            out["overtake_duty_when_allowed"] = np.nan

        # SOC impact: store change while overtake is active vs rest of lap
        if "ers_store_mj" in lap.columns and lap["ot_active"].any() and (~lap["ot_active"]).any():
            store = lap["ers_store_mj"].astype(float)
            dstore = store.diff().fillna(0.0)
            active = dstore[lap["ot_active"]]
            idle = dstore[~lap["ot_active"]]
            out["overtake_soc_rate_mj"] = float(active.mean())
            out["overtake_soc_delta_mj"] = float(active.sum())
            out["baseline_soc_rate_mj"] = float(idle.mean())
            out["overtake_soc_extra_mj"] = float(active.sum() - idle.mean() * len(active))

    if "ice_kw" in lap.columns and lap["ice_kw"].notna().any():
        out["ice_avg_kw"] = float(lap["ice_kw"].mean())
        out["ice_peak_kw"] = float(lap["ice_kw"].max())
    if "mguk_kw" in lap.columns and lap["mguk_kw"].notna().any():
        out["mguk_avg_kw"] = float(lap["mguk_kw"].mean())
        out["mguk_peak_kw"] = float(lap["mguk_kw"].max())
        out["mguk_share_pct"] = float(lap["mguk_share"].mean() * 100) if "mguk_share" in lap.columns else np.nan
        if "throttle" in lap.columns:
            wot = lap["throttle"] > 0.95
            if wot.any():
                out["wot_mguk_share_pct"] = float(lap.loc[wot, "mguk_share"].mean() * 100)
                out["wot_mguk_avg_kw"] = float(lap.loc[wot, "mguk_kw"].mean())
                out["wot_ice_avg_kw"] = float(lap.loc[wot, "ice_kw"].mean()) if "ice_kw" in lap.columns else np.nan

    out["samples"] = int(n)
    return {k: v for k, v in out.items() if v is not None}


def active_aero_by_distance(lap_df: pd.DataFrame, n_bins: int = 24) -> pd.DataFrame:
    """Low-drag aero share along the lap."""
    lap = enrich_2026_channels(lap_df)
    if lap.empty or "lap_distance" not in lap.columns or "activeAero_mode" not in lap.columns:
        return pd.DataFrame()

    length = float(lap["lap_distance"].max())
    edges = np.linspace(0, length, n_bins + 1)
    rows = []
    for i in range(n_bins):
        mask = (lap["lap_distance"] >= edges[i]) & (
            lap["lap_distance"] <= edges[i + 1] if i == n_bins - 1 else lap["lap_distance"] < edges[i + 1]
        )
        chunk = lap.loc[mask]
        if chunk.empty:
            continue
        rows.append(
            {
                "bin": i + 1,
                "dist_start": float(edges[i]),
                "dist_end": float(edges[i + 1]),
                "dist_mid": float((edges[i] + edges[i + 1]) / 2),
                "low_drag_pct": float(chunk["aero_low_drag"].mean() * 100),
                "speed_avg": float(chunk["speed"].mean()) if "speed" in chunk else np.nan,
                "throttle_avg": float(chunk["throttle"].mean()) if "throttle" in chunk else np.nan,
            }
        )
    return pd.DataFrame(rows)


def compare_active_aero(focus: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """Align aero distance bins; positive delta => focus spent more time in low-drag."""
    if focus.empty or reference.empty:
        return pd.DataFrame()
    merged = focus.merge(
        reference[["bin", "low_drag_pct"]].rename(columns={"low_drag_pct": "ref_low_drag_pct"}),
        on="bin",
        how="left",
    )
    merged["low_drag_delta"] = merged["low_drag_pct"] - merged["ref_low_drag_pct"]
    return merged


def power_split_by_distance(lap_df: pd.DataFrame, n_bins: int = 24) -> pd.DataFrame:
    """ICE vs MGUK average power along the lap."""
    lap = enrich_2026_channels(lap_df)
    if lap.empty or "lap_distance" not in lap.columns:
        return pd.DataFrame()
    if "ice_kw" not in lap.columns and "mguk_kw" not in lap.columns:
        return pd.DataFrame()
    if lap[["ice_kw", "mguk_kw"]].isna().all().all():
        return pd.DataFrame()

    length = float(lap["lap_distance"].max())
    edges = np.linspace(0, length, n_bins + 1)
    rows = []
    for i in range(n_bins):
        mask = (lap["lap_distance"] >= edges[i]) & (
            lap["lap_distance"] <= edges[i + 1] if i == n_bins - 1 else lap["lap_distance"] < edges[i + 1]
        )
        chunk = lap.loc[mask]
        if chunk.empty:
            continue
        ice = float(chunk["ice_kw"].mean()) if "ice_kw" in chunk else np.nan
        mguk = float(chunk["mguk_kw"].mean()) if "mguk_kw" in chunk else np.nan
        total = (0.0 if np.isnan(ice) else ice) + (0.0 if np.isnan(mguk) else mguk)
        rows.append(
            {
                "bin": i + 1,
                "dist_start": float(edges[i]),
                "dist_end": float(edges[i + 1]),
                "dist_mid": float((edges[i] + edges[i + 1]) / 2),
                "ice_kw": ice,
                "mguk_kw": mguk,
                "total_kw": total,
                "mguk_share_pct": float(mguk / total * 100) if total > 1.0 else np.nan,
                "speed_avg": float(chunk["speed"].mean()) if "speed" in chunk else np.nan,
                "throttle_avg": float(chunk["throttle"].mean()) if "throttle" in chunk else np.nan,
                "overtake_pct": float(chunk["ot_active"].mean() * 100) if "ot_active" in chunk else np.nan,
            }
        )
    return pd.DataFrame(rows)


def overtake_timeline(lap_df: pd.DataFrame) -> pd.DataFrame:
    """Distance-indexed overtake / allowed / SOC for plotting."""
    lap = enrich_2026_channels(lap_df)
    if lap.empty:
        return pd.DataFrame()
    cols = [c for c in ("lap_distance", "ot_allowed", "ot_active", "ers_store_mj", "speed", "throttle") if c in lap.columns]
    if "lap_distance" not in cols:
        return pd.DataFrame()
    out = lap[cols].copy()
    if "ot_allowed" in out.columns:
        out["ot_allowed"] = out["ot_allowed"].astype(float)
    if "ot_active" in out.columns:
        out["ot_active"] = out["ot_active"].astype(float)
    return out


@per_frame()
def session_2026_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per valid lap with 2026 channel KPIs."""
    summary = build_lap_summary(df)
    if summary.empty:
        return pd.DataFrame()

    rows = []
    for _, row in summary.iterrows():
        lap = get_lap(df, int(row["lap"]))
        kpis = lap_2026_summary(lap)
        if not kpis:
            continue
        rows.append(
            {
                "lap": int(row["lap"]),
                "lap_time": float(row["lap_time"]),
                "delta_best": float(row.get("delta_best") or 0),
                "is_best": bool(row.get("is_best")),
                **kpis,
            }
        )
    return pd.DataFrame(rows)


def channels_2026_insights(
    df: pd.DataFrame,
    focus_lap: int,
    reference_lap: int | None = None,
) -> list[ErsTip]:
    """Coach callouts for active aero, overtake, and ICE/MGUK split."""
    tips: list[ErsTip] = []
    table = session_2026_table(df)
    focus_df = enrich_2026_channels(get_lap(df, focus_lap))
    focus_k = lap_2026_summary(focus_df)

    if not focus_k:
        return [ErsTip("warning", "No 2026 channels", "This lap has no activeAero / overtake / ICE–MGUK columns.")]

    ref_lap = reference_lap
    if ref_lap is None and not table.empty and table["is_best"].any():
        ref_lap = int(table.loc[table["is_best"], "lap"].iloc[0])
    ref_k = lap_2026_summary(get_lap(df, int(ref_lap))) if ref_lap is not None else {}

    if "aero_low_drag_pct" in focus_k:
        tips.append(
            ErsTip(
                "info",
                "Active aero window",
                f"Lap {focus_lap}: low-drag {focus_k['aero_low_drag_pct']:.0f}% of the lap"
                + (
                    f" (avg {focus_k['aero_low_drag_speed']:.0f} km/h) vs high-DF "
                    f"{focus_k.get('aero_high_df_speed', float('nan')):.0f} km/h."
                    if pd.notna(focus_k.get("aero_low_drag_speed"))
                    else "."
                ),
            )
        )
        if ref_k and "aero_low_drag_pct" in ref_k and ref_lap != focus_lap:
            delta = focus_k["aero_low_drag_pct"] - ref_k["aero_low_drag_pct"]
            if abs(delta) >= 5:
                tips.append(
                    ErsTip(
                        "tip" if delta < 0 else "info",
                        "Aero vs reference",
                        f"{'Less' if delta < 0 else 'More'} low-drag than lap {ref_lap} "
                        f"({delta:+.0f} pts). Check straights: leave low-drag open on long DRS zones; "
                        "switch early into braking if you are unstable on entry.",
                    )
                )

        focus_prof = active_aero_by_distance(focus_df, n_bins=12)
        if not focus_prof.empty and focus_prof["low_drag_pct"].max() < 20:
            tips.append(
                ErsTip(
                    "tip",
                    "Little low-drag aero",
                    "Low-drag mode rarely engaged. On 2026 cars that costs top speed — "
                    "confirm the active-aero toggle on the longest straights.",
                )
            )

    if "overtake_allowed_pct" in focus_k or "overtake_used_pct" in focus_k:
        allowed = focus_k.get("overtake_allowed_pct", 0.0)
        used = focus_k.get("overtake_used_pct", 0.0)
        duty = focus_k.get("overtake_duty_when_allowed", np.nan)
        # Constant flags (always 0 or always 1) → low-signal dump; still report once.
        const_signal = (allowed in (0.0, 100.0)) and (used in (0.0, 100.0)) and abs(allowed - used) < 1e-6
        if const_signal:
            tips.append(
                ErsTip(
                    "info",
                    "Overtake channel flat",
                    f"Overtake / allowed stayed at {'ON' if used > 50 else 'OFF'} for the whole lap "
                    f"({used:.0f}% samples). Export may not toggle mid-lap in this session — "
                    "SOC / deploy mode remain the better energy signals.",
                )
            )
        else:
            tips.append(
                ErsTip(
                    "info",
                    "Overtake availability",
                    f"Allowed {allowed:.0f}% of the lap, used {used:.0f}%"
                    + (f" (duty when available {duty:.0f}%)." if pd.notna(duty) else "."),
                )
            )
            unused = focus_k.get("overtake_unused_pct", 0.0)
            if unused > 8 and allowed > 10:
                tips.append(
                    ErsTip(
                        "tip",
                        "Overtake left on the table",
                        f"~{unused:.0f}% of samples were allowed but not pressed. "
                        "Use the button on exit / DRS detection when SOC supports it.",
                    )
                )
            if pd.notna(focus_k.get("overtake_soc_delta_mj")) and abs(focus_k["overtake_soc_delta_mj"]) > 0.05:
                delta = focus_k["overtake_soc_delta_mj"]
                tips.append(
                    ErsTip(
                        "info",
                        "Overtake SOC impact",
                        f"While overtake was active, store changed by {delta:+.2f} MJ "
                        f"(~{focus_k.get('overtake_soc_rate_mj', 0):+.4f} MJ/sample). "
                        + (
                            "Expect a steeper dump — plan harvest before the next attack."
                            if delta < 0
                            else "Net store rose during overtake windows (check harvest overlap)."
                        ),
                    )
                )

    if "mguk_share_pct" in focus_k and pd.notna(focus_k["mguk_share_pct"]):
        tips.append(
            ErsTip(
                "info",
                "ICE / MGUK split",
                f"Avg ICE {focus_k.get('ice_avg_kw', float('nan')):.0f} kW · "
                f"MGUK {focus_k.get('mguk_avg_kw', float('nan')):.0f} kW "
                f"(MGUK share {focus_k['mguk_share_pct']:.0f}% of total)."
                + (
                    f" On WOT, MGUK share {focus_k['wot_mguk_share_pct']:.0f}%."
                    if pd.notna(focus_k.get("wot_mguk_share_pct"))
                    else ""
                ),
            )
        )
        if ref_k and pd.notna(ref_k.get("wot_mguk_share_pct")) and pd.notna(focus_k.get("wot_mguk_share_pct")):
            gap = focus_k["wot_mguk_share_pct"] - ref_k["wot_mguk_share_pct"]
            if gap < -8:
                tips.append(
                    ErsTip(
                        "tip",
                        "Weak electric on the straights",
                        f"WOT MGUK share is {gap:.0f} pts vs lap {ref_lap}. "
                        "Build SOC earlier or hold a deploy pulse for the longest straight.",
                    )
                )

        prof = power_split_by_distance(focus_df, n_bins=12)
        if not prof.empty and prof["mguk_kw"].notna().any():
            peak = prof.sort_values("mguk_kw", ascending=False).iloc[0]
            tips.append(
                ErsTip(
                    "info",
                    "Peak MGUK zone",
                    f"Strongest electric assist around {peak['dist_start']:.0f}–{peak['dist_end']:.0f} m "
                    f"(~{peak['mguk_kw']:.0f} kW avg in bin).",
                )
            )

    return tips
