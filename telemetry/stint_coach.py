"""Tyre and fuel saving techniques derived from session telemetry."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .channels import WHEELS
from .coach_constants import LOCKUP_BRAKE_THRESHOLD
from .framecache import per_frame
from .metrics import build_lap_summary, get_lap


@dataclass
class StintTip:
    severity: str  # info | tip | warning
    title: str
    detail: str
    category: str  # tyre | fuel | technique


def _wear_delta(lap_df: pd.DataFrame) -> float | None:
    cols = [f"tyre_wear_{i}" for i in range(4) if f"tyre_wear_{i}" in lap_df.columns]
    if not cols:
        return None
    # SRT sometimes reports remaining life; use abs change averaged
    deltas = []
    for c in cols:
        a = float(lap_df[c].iloc[0])
        b = float(lap_df[c].iloc[-1])
        deltas.append(abs(b - a))
    return float(np.mean(deltas) * 100)


def _temp_balance(lap_df: pd.DataFrame) -> dict | None:
    cols = [f"tyre_temp_{i}" for i in range(4) if f"tyre_temp_{i}" in lap_df.columns]
    if len(cols) < 4:
        return None
    labels = list(WHEELS)
    temps = {lab: float(lap_df[f"tyre_temp_{i}"].mean()) for i, lab in enumerate(labels)}
    vals = list(temps.values())
    return {
        "temps": temps,
        "avg": float(np.mean(vals)),
        "spread": float(np.max(vals) - np.min(vals)),
        "hottest": max(temps, key=temps.get),
        "coldest": min(temps, key=temps.get),
    }


@per_frame()
def session_stint_table(df: pd.DataFrame) -> pd.DataFrame:
    summary = build_lap_summary(df)
    if summary.empty:
        return pd.DataFrame()

    rows = []
    for _, row in summary.iterrows():
        lap_n = int(row["lap"])
        lap = get_lap(df, lap_n)
        wear = _wear_delta(lap)
        fuel_used = float(row["fuel_used"]) if "fuel_used" in row and pd.notna(row["fuel_used"]) else None
        if fuel_used is None and "fuel" in lap.columns:
            fuel_used = float(lap["fuel"].iloc[0] - lap["fuel"].iloc[-1])

        # Input harshness proxies
        thr_std = float(lap["throttle"].diff().abs().mean()) if "throttle" in lap.columns else np.nan
        brk_std = float(lap["brake"].diff().abs().mean()) if "brake" in lap.columns else np.nan
        coast = float(row["coast_pct"]) if "coast_pct" in row and pd.notna(row["coast_pct"]) else (
            float(lap["coasting"].mean() * 100) if "coasting" in lap.columns else np.nan
        )
        lockups = int(row["lockup_samples"]) if "lockup_samples" in row and pd.notna(row["lockup_samples"]) else (
            int(lap["lockup_risk"].sum()) if "lockup_risk" in lap.columns else 0
        )
        temps = _temp_balance(lap)

        rows.append(
            {
                "lap": lap_n,
                "lap_time": float(row["lap_time"]),
                "fuel_used": fuel_used,
                "wear_delta_pct": wear,
                "tyre_temp_avg": temps["avg"] if temps else np.nan,
                "tyre_temp_spread": temps["spread"] if temps else np.nan,
                "coast_pct": coast,
                "throttle_jerk": thr_std,
                "brake_jerk": brk_std,
                "lockup_samples": lockups,
                "is_best": bool(row.get("is_best")),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out

    # Efficiency scores vs session medians
    med_fuel = float(out["fuel_used"].median()) if out["fuel_used"].notna().any() else np.nan
    med_wear = float(out["wear_delta_pct"].median()) if out["wear_delta_pct"].notna().any() else np.nan
    best_t = float(out["lap_time"].min())
    out["fuel_vs_med"] = out["fuel_used"] - med_fuel if pd.notna(med_fuel) else np.nan
    out["wear_vs_med"] = out["wear_delta_pct"] - med_wear if pd.notna(med_wear) else np.nan
    out["pace_delta"] = out["lap_time"] - best_t
    # Sweet-spot: close to best pace with below-median fuel/wear
    out["stint_score"] = (
        100
        - out["pace_delta"].clip(lower=0) * 25
        - out["fuel_vs_med"].fillna(0).clip(lower=0) * 40
        - out["wear_vs_med"].fillna(0).clip(lower=0) * 3
    ).clip(0, 100)
    return out


def stint_saving_insights(
    df: pd.DataFrame,
    focus_lap: int,
    reference_lap: int | None = None,
    conditions: str | None = None,
) -> list[StintTip]:
    from .conditions import STATE_LABELS, _as_state, is_wet_surface, weather_banner

    tips: list[StintTip] = []
    state = _as_state(conditions)
    banner = weather_banner(state)
    if banner:
        tips.append(StintTip("info", f"Track state: {STATE_LABELS[state]}", banner, "weather"))

    table = session_stint_table(df)
    if table.empty:
        return tips + [StintTip("warning", "No stint data", "Need fuel/tyre channels in the session.", "tyre")]

    focus_rows = table[table["lap"] == focus_lap]
    if focus_rows.empty:
        return tips + [StintTip("warning", "Lap missing", f"Lap {focus_lap} not found.", "technique")]
    focus = focus_rows.iloc[0]
    best = table.loc[table["is_best"]].iloc[0]
    ref_lap = reference_lap if reference_lap is not None else int(best["lap"])
    ref = table[table["lap"] == ref_lap].iloc[0] if (table["lap"] == ref_lap).any() else best

    wet = is_wet_surface(state)
    hot_lim = 88 if state == "wet" else 95
    if state == "wet":
        cold_lim = 42
    elif wet:
        cold_lim = 55
    else:
        cold_lim = 70

    # Fuel
    if pd.notna(focus.get("fuel_used")) and pd.notna(table["fuel_used"].median()):
        med = float(table["fuel_used"].median())
        tips.append(
            StintTip(
                "info",
                "Fuel this lap",
                f"Used {focus['fuel_used']:.2f} units (session median {med:.2f}). "
                f"Best lap used {best['fuel_used']:.2f}.",
                "fuel",
            )
        )
        if focus["fuel_used"] > med * 1.15 and focus["lap_time"] > best["lap_time"] + 0.4:
            tips.append(
                StintTip(
                    "tip",
                    "Burning fuel without the lap time",
                    "Fuel use is high while pace is off. Shorten full-throttle time on low-ROI zones "
                    "and add a short lift-coast before heavy braking — saves fuel with little time loss.",
                    "fuel",
                )
            )
        if focus["fuel_used"] > best["fuel_used"] * 1.2 and focus["lap"] == best["lap"]:
            tips.append(
                StintTip(
                    "info",
                    "Push lap fuel cost",
                    "Your fastest lap burned clearly more fuel. For race sims, copy the median-fuel laps' "
                    "throttle discipline and only 'overspend' when attacking/defending.",
                    "fuel",
                )
            )

    # Coasting / lift-and-coast
    if pd.notna(focus.get("coast_pct")):
        if focus["coast_pct"] < 4 and focus["fuel_used"] > table["fuel_used"].median():
            tips.append(
                StintTip(
                    "tip",
                    "Little lift-and-coast",
                    f"Only {focus['coast_pct']:.1f}% coasting. Try a 30–50 m lift before big brake zones "
                    "(T1 / end of DRS). In 2026 cars this also helps ERS harvest.",
                    "fuel",
                )
            )
        elif focus["coast_pct"] > 12 and focus["lap_time"] > best["lap_time"] + 0.5:
            tips.append(
                StintTip(
                    "tip",
                    "Coasting too early",
                    f"Coast share is high ({focus['coast_pct']:.1f}%) and pace suffers. "
                    "Keep coasting short and late — save fuel without killing mid-corner minimum speeds.",
                    "technique",
                )
            )

    # Tyre temps / balance
    focus_lap_df = get_lap(df, focus_lap)
    temps = _temp_balance(focus_lap_df)
    if temps:
        tips.append(
            StintTip(
                "info",
                "Tyre temperatures",
                f"Avg {temps['avg']:.0f}°C, spread {temps['spread']:.0f}°C "
                f"({temps['hottest']} hot / {temps['coldest']} cold).",
                "tyre",
            )
        )
        if temps["spread"] > 12:
            tips.append(
                StintTip(
                    "warning",
                    "Tyre temp imbalance",
                    f"{temps['hottest']} is overloaded vs {temps['coldest']}. "
                    "Ease entry on that side, check pressures/toe, or soften that-axle ARB one click "
                    "(camber stays at meta max negative).",
                    "tyre",
                )
            )
        if temps["avg"] > hot_lim:
            tips.append(
                StintTip(
                    "tip",
                    "Tyres running hot",
                    (
                        "Wet/inter surfaces usually run cooler — if temps are this high, you're sliding. "
                        "Calm inputs, earlier throttle, and a small pressure rise."
                        if wet
                        else "Average surface temp is high. Reduce sliding (earlier throttle, less oversteer), "
                        "raise pressures slightly if graining/overheating, and avoid mid-corner partial throttle fights."
                    ),
                    "tyre",
                )
            )
        elif temps["avg"] < cold_lim:
            if wet:
                tips.append(
                    StintTip(
                        "info",
                        "Cool surface temps",
                        f"Avg {temps['avg']:.0f}°C is normal for {STATE_LABELS[state]}. "
                        "Don't drop pressures like dry slicks — build temp with commitment, not weave alone.",
                        "tyre",
                    )
                )
            else:
                tips.append(
                    StintTip(
                        "tip",
                        "Tyres under window",
                        "Temps look cool — you'll lack grip. Warm-up with a weave / push sector, "
                        "or lower pressures a step if the compound never comes in.",
                        "tyre",
                    )
                )

    if wet:
        tips.append(
            StintTip(
                "tip",
                "Wet technique",
                "Brake earlier and straighter, feed throttle later, and prioritise exits over apex speed. "
                "Standing water = lift early on kerbs and painted lines.",
                "technique",
            )
        )

    # Wear / lockups
    if pd.notna(focus.get("wear_delta_pct")) and focus["wear_delta_pct"] > 0:
        med_w = float(table["wear_delta_pct"].median())
        tips.append(
            StintTip(
                "info",
                "Tyre wear this lap",
                f"~{focus['wear_delta_pct']:.2f}% wear delta (median {med_w:.2f}%).",
                "tyre",
            )
        )
    if focus.get("lockup_samples", 0) > LOCKUP_BRAKE_THRESHOLD:
        tips.append(
            StintTip(
                "warning",
                "Lock-ups eating tyres",
                f"~{int(focus['lockup_samples'])} high-slip braking samples. "
                "Drop brake pressure a few %, and if the car snaps on entry move bias forward — "
                "rearward bias makes light brake inputs spin you.",
                "tyre",
            )
        )

    # Input smoothness
    if pd.notna(focus.get("throttle_jerk")) and pd.notna(ref.get("throttle_jerk")):
        if focus["throttle_jerk"] > ref["throttle_jerk"] * 1.25:
            tips.append(
                StintTip(
                    "tip",
                    "Spiky throttle",
                    "Throttle changes are harsher than the reference lap. Smoother application on exit "
                    "cuts rear wear and often improves traction (free lap time + tyre life).",
                    "technique",
                )
            )
    if pd.notna(focus.get("brake_jerk")) and pd.notna(ref.get("brake_jerk")):
        if focus["brake_jerk"] > ref["brake_jerk"] * 1.25:
            tips.append(
                StintTip(
                    "tip",
                    "Spiky braking",
                    "Brake trace is choppier than reference. Aim for one progressive press → trail off; "
                    "saves fronts and keeps the nose settled for turn-in.",
                    "technique",
                )
            )

    # Best efficiency lap recommendation
    if len(table) >= 3 and "stint_score" in table.columns:
        eff = table.sort_values("stint_score", ascending=False).iloc[0]
        tips.append(
            StintTip(
                "tip",
                "Copy this management lap",
                f"Lap {int(eff['lap'])} scores best for pace vs fuel/tyre cost "
                f"(time {eff['lap_time']:.3f}s, fuel {eff['fuel_used']:.2f}, "
                f"stint score {eff['stint_score']:.0f}). Use it as your race-sim reference.",
                "technique",
            )
        )

    # Race-craft checklist
    tips.append(
        StintTip(
            "info",
            "Race-saving checklist",
            "1) Lift-coast before big stops  2) One clean brake press  3) Progressive exit throttle  "
            "4) Deploy ERS on straights not mid-corner  5) Don’t fight a slide — collect and reapply.",
            "technique",
        )
    )
    return tips


def session_stint_insights(
    df: pd.DataFrame,
    *,
    best_lap: int | None = None,
    conditions: str | None = None,
) -> list[StintTip]:
    """Stint-wide fuel/tyre/technique patterns — not a single lap."""
    from .conditions import STATE_LABELS, _as_state, is_wet_surface, weather_banner

    tips: list[StintTip] = []
    state = _as_state(conditions)
    banner = weather_banner(state)
    if banner:
        tips.append(StintTip("info", f"Track state: {STATE_LABELS[state]}", banner, "weather"))

    table = session_stint_table(df)
    if table.empty:
        return tips + [StintTip("warning", "No stint data", "Need fuel/tyre channels in the session.", "tyre")]

    if best_lap is None:
        best_lap = int(table.loc[table["is_best"], "lap"].iloc[0])
    best = table.loc[table["lap"] == best_lap].iloc[0] if (table["lap"] == best_lap).any() else table.loc[table["is_best"]].iloc[0]

    n = len(table)
    med_fuel = float(table["fuel_used"].median()) if table["fuel_used"].notna().any() else None
    med_coast = float(table["coast_pct"].median()) if table["coast_pct"].notna().any() else None
    spread = float(table["lap_time"].max() - table["lap_time"].min())

    if spread >= 0.9 and n >= 4:
        tips.append(
            StintTip(
                "tip",
                "Pace inconsistency",
                f"Lap times spread {spread:.2f}s across {n} laps — pick one reference line (PB L{int(best['lap'])}) "
                "and repeat it instead of chasing one-off hero laps.",
                "technique",
            )
        )

    if med_fuel is not None:
        heavy = table[(table["fuel_used"] > med_fuel * 1.12) & (table["lap_time"] > best["lap_time"] + 0.35)]
        if len(heavy) >= max(2, n // 3):
            tips.append(
                StintTip(
                    "tip",
                    "Fuel burn without pace",
                    f"{len(heavy)}/{n} laps used more fuel than median without matching PB pace. "
                    "Shorten full-throttle time and add brief lift-coast before big stops.",
                    "fuel",
                )
            )

    if med_coast is not None and med_coast < 4 and med_fuel is not None and table["fuel_used"].median() > best["fuel_used"]:
        tips.append(
            StintTip(
                "tip",
                "Session lift-coast headroom",
                f"Median coasting is only {med_coast:.1f}% while fuel use sits above your PB lap. "
                "A little lift-and-coast before heavy braking saves fuel with minimal lap-time cost.",
                "fuel",
            )
        )

    if "wear_delta_pct" in table.columns and table["wear_delta_pct"].notna().sum() >= 4:
        wear = table.dropna(subset=["wear_delta_pct"]).sort_values("lap")
        if len(wear) >= 4:
            first = float(wear.head(2)["wear_delta_pct"].mean())
            last = float(wear.tail(2)["wear_delta_pct"].mean())
            if last > first * 1.35 and last > 0.15:
                tips.append(
                    StintTip(
                        "warning",
                        "Tyre deg ramping",
                        f"Wear per lap is rising ({first:.2f}% → {last:.2f}% avg). "
                        "Calm mid-corner slides and avoid repeated lockups — deg often beats raw pace in race sims.",
                        "tyre",
                    )
                )

    lock_laps = int((table["lockup_samples"] > LOCKUP_BRAKE_THRESHOLD).sum()) if "lockup_samples" in table.columns else 0
    if lock_laps >= max(2, n // 3):
        tips.append(
            StintTip(
                "warning",
                "Lockups across the stint",
                f"Heavy lockups on {lock_laps}/{n} laps — move brake markers out session-wide or ease initial pressure.",
                "technique",
            )
        )

    if n >= 3 and "stint_score" in table.columns:
        eff = table.sort_values("stint_score", ascending=False).iloc[0]
        tips.append(
            StintTip(
                "tip",
                "Best race-sim reference lap",
                f"L{int(eff['lap'])} balances pace vs cost best ({eff['lap_time']:.3f}s, fuel {eff['fuel_used']:.2f}). "
                "Copy its inputs for long-run targets.",
                "technique",
            )
        )

    if is_wet_surface(state):
        tips.append(
            StintTip(
                "tip",
                "Wet stint discipline",
                "Session average: brake earlier, straighter, and feed throttle later. "
                "Consistency beats single-lap heroics on low grip.",
                "technique",
            )
        )

    return tips

