"""Fuel and tyre race-window projections from session stint telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .framecache import per_frame
from .metrics import build_lap_summary, get_lap
from .stint_coach import StintTip, session_stint_table


@dataclass
class FuelWindow:
    fuel_remaining: float | None
    fuel_per_lap: float | None
    laps_possible: float | None
    target_laps: int | None
    laps_in_hand: float | None
    race_distance_m: float | None
    track_length_m: float | None
    distance_remaining_m: float | None
    projected_finish_fuel: float | None
    status: str  # ok | tight | short | unknown
    notes: list[str] = field(default_factory=list)


@dataclass
class TyreCliff:
    current_wear_pct: float | None
    wear_per_lap: float | None
    cliff_wear_pct: float
    laps_to_cliff: float | None
    temp_trend_c_per_lap: float | None
    temp_avg: float | None
    cliff_risk: str  # low | rising | cliff | unknown
    stint_laps: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class StintWindows:
    fuel: FuelWindow
    tyre: TyreCliff
    stint_table: pd.DataFrame
    projection: pd.DataFrame


def _valid_stint_rows(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return table
    out = table.copy()
    # Drop absurd wear (flashback / invalid -1 compound samples)
    if "wear_delta_pct" in out.columns:
        out = out[out["wear_delta_pct"].isna() | ((out["wear_delta_pct"] >= 0) & (out["wear_delta_pct"] < 40))]
    if "fuel_used" in out.columns:
        out = out[out["fuel_used"].isna() | ((out["fuel_used"] > 0) & (out["fuel_used"] < 20))]
    return out.reset_index(drop=True)


def _detect_stint_segments(summary: pd.DataFrame, wear_reset_drop: float = 15.0) -> list[list[int]]:
    """Split race into stints on new tyre sets (tyres.tyre_stints); wear-reset fallback for bare summaries."""
    if summary.empty or "lap" not in summary.columns:
        return []
    if "fresh_set" in summary.columns:
        from .tyres import tyre_stints

        return [s.laps for s in tyre_stints(summary)]
    laps = summary.sort_values("lap")
    if "tyre_wear_avg" not in laps.columns or laps["tyre_wear_avg"].isna().all():
        return [laps["lap"].astype(int).tolist()]

    segments: list[list[int]] = []
    current: list[int] = []
    prev_wear: float | None = None
    for _, row in laps.iterrows():
        lap_n = int(row["lap"])
        wear = float(row["tyre_wear_avg"]) if pd.notna(row["tyre_wear_avg"]) else None
        if wear is not None and wear < 0:
            wear = None
        if (
            current
            and prev_wear is not None
            and wear is not None
            and (prev_wear - wear) >= wear_reset_drop
        ):
            segments.append(current)
            current = [lap_n]
        else:
            current.append(lap_n)
        if wear is not None:
            prev_wear = wear
    if current:
        segments.append(current)
    return segments or [laps["lap"].astype(int).tolist()]


def project_fuel_window(
    df: pd.DataFrame,
    target_laps: int | None = None,
    race_distance_m: float | None = None,
    track_length_m: float | None = None,
    remaining_fuel: float | None = None,
) -> FuelWindow:
    """
    Project remaining fuel to a target lap count or remaining race distance.

    Uses median fuel_used from session_stint_table (robust to push/save outliers).
    """
    notes: list[str] = []
    table = _valid_stint_rows(session_stint_table(df))
    summary = build_lap_summary(df)

    fuel_per_lap = None
    if not table.empty and table["fuel_used"].notna().any():
        fuel_per_lap = float(table["fuel_used"].median())
        notes.append(f"Median burn {fuel_per_lap:.2f} units/lap from {table['fuel_used'].notna().sum()} laps.")

    if remaining_fuel is None and not summary.empty and "fuel_end" in summary.columns:
        last = summary.sort_values("lap").iloc[-1]
        if pd.notna(last.get("fuel_end")):
            remaining_fuel = float(last["fuel_end"])

    length = track_length_m
    if length is None and "lap_distance" in df.columns and not df.empty:
        length = float(df["lap_distance"].max())

    # Infer target laps from race distance if needed
    if target_laps is None and race_distance_m and length and length > 0:
        target_laps = int(np.ceil(race_distance_m / length))
        notes.append(f"Target {target_laps} laps from {race_distance_m:.0f} m / {length:.0f} m.")

    laps_done = int(summary["lap"].nunique()) if not summary.empty else 0
    laps_remaining_target = None
    if target_laps is not None:
        laps_remaining_target = max(0, int(target_laps) - laps_done)

    laps_possible = None
    if fuel_per_lap and fuel_per_lap > 1e-6 and remaining_fuel is not None:
        laps_possible = float(remaining_fuel / fuel_per_lap)

    laps_in_hand = None
    projected_finish = None
    if laps_possible is not None and laps_remaining_target is not None:
        laps_in_hand = float(laps_possible - laps_remaining_target)
        if fuel_per_lap is not None and remaining_fuel is not None:
            projected_finish = float(remaining_fuel - fuel_per_lap * laps_remaining_target)

    distance_remaining = None
    if race_distance_m is not None and length and not summary.empty:
        # Approximate distance covered as completed flying laps * length
        distance_remaining = max(0.0, float(race_distance_m) - laps_done * float(length))
    elif laps_remaining_target is not None and length:
        distance_remaining = float(laps_remaining_target) * float(length)

    status = "unknown"
    if laps_in_hand is not None:
        if laps_in_hand >= 1.5:
            status = "ok"
        elif laps_in_hand >= 0:
            status = "tight"
        else:
            status = "short"
    elif laps_possible is not None:
        status = "ok" if laps_possible >= 3 else "tight"

    return FuelWindow(
        fuel_remaining=remaining_fuel,
        fuel_per_lap=fuel_per_lap,
        laps_possible=laps_possible,
        target_laps=target_laps,
        laps_in_hand=laps_in_hand,
        race_distance_m=race_distance_m,
        track_length_m=float(length) if length else None,
        distance_remaining_m=distance_remaining,
        projected_finish_fuel=projected_finish,
        status=status,
        notes=notes,
    )


def project_tyre_cliff(
    df: pd.DataFrame,
    cliff_wear_pct: float = 55.0,
    temp_hot_c: float = 95.0,
) -> TyreCliff:
    """
    Project laps until tyre wear hits a cliff threshold using the current stint trend.

    Wear is end-of-lap average % from build_lap_summary; rate from per-lap wear_delta.
    Temp trend from session_stint_table tyre_temp_avg slope (overheating accelerates cliff).
    """
    notes: list[str] = []
    summary = build_lap_summary(df)
    table = _valid_stint_rows(session_stint_table(df))
    if summary.empty:
        return TyreCliff(None, None, cliff_wear_pct, None, None, None, "unknown", [], ["No lap summary."])

    segments = _detect_stint_segments(summary)
    stint_laps = segments[-1] if segments else []
    notes.append(f"Current stint: laps {stint_laps[0]}–{stint_laps[-1]} ({len(stint_laps)} laps).")

    stint_sum = summary[summary["lap"].isin(stint_laps)].sort_values("lap")
    stint_tbl = table[table["lap"].isin(stint_laps)] if not table.empty else table

    current_wear = None
    if "tyre_wear_avg" in stint_sum.columns and stint_sum["tyre_wear_avg"].notna().any():
        current_wear = float(stint_sum["tyre_wear_avg"].iloc[-1])

    wear_per_lap = None
    if not stint_tbl.empty and stint_tbl["wear_delta_pct"].notna().any():
        wear_per_lap = float(stint_tbl["wear_delta_pct"].median())
        notes.append(f"Median wear {wear_per_lap:.2f}% / lap this stint.")
    elif current_wear is not None and len(stint_sum) >= 2:
        first_wear = float(stint_sum["tyre_wear_avg"].iloc[0])
        n = max(1, len(stint_sum) - 1)
        wear_per_lap = max(0.0, (current_wear - first_wear) / n)

    laps_to_cliff = None
    if current_wear is not None and wear_per_lap and wear_per_lap > 1e-6:
        remaining = cliff_wear_pct - current_wear
        laps_to_cliff = float(remaining / wear_per_lap) if remaining > 0 else 0.0

    temp_avg = None
    temp_trend = None
    if not stint_tbl.empty and stint_tbl["tyre_temp_avg"].notna().sum() >= 2:
        temps = stint_tbl.sort_values("lap")
        temp_avg = float(temps["tyre_temp_avg"].iloc[-1])
        x = temps["lap"].astype(float).to_numpy()
        y = temps["tyre_temp_avg"].astype(float).to_numpy()
        if len(x) >= 2 and np.std(x) > 0:
            temp_trend = float(np.polyfit(x, y, 1)[0])
            notes.append(f"Temp trend {temp_trend:+.1f} °C/lap (now {temp_avg:.0f} °C).")

    cliff_risk = "unknown"
    if laps_to_cliff is not None:
        hot = temp_avg is not None and temp_avg >= temp_hot_c
        rising = temp_trend is not None and temp_trend > 1.5
        if laps_to_cliff <= 0 or current_wear is not None and current_wear >= cliff_wear_pct:
            cliff_risk = "cliff"
            notes.append("Wear already at / past cliff threshold.")
        elif laps_to_cliff <= 3 or (hot and laps_to_cliff <= 5):
            cliff_risk = "rising"
        elif rising and laps_to_cliff <= 6:
            cliff_risk = "rising"
            notes.append("Temps climbing — cliff may arrive earlier than wear-only projection.")
        else:
            cliff_risk = "low"

    return TyreCliff(
        current_wear_pct=current_wear,
        wear_per_lap=wear_per_lap,
        cliff_wear_pct=cliff_wear_pct,
        laps_to_cliff=laps_to_cliff,
        temp_trend_c_per_lap=temp_trend,
        temp_avg=temp_avg,
        cliff_risk=cliff_risk,
        stint_laps=stint_laps,
        notes=notes,
    )


def build_window_projection(
    df: pd.DataFrame,
    fuel: FuelWindow,
    tyre: TyreCliff,
    horizon_laps: int = 15,
) -> pd.DataFrame:
    """Forward table: projected fuel + wear for the next N laps from current state."""
    summary = build_lap_summary(df)
    if summary.empty:
        return pd.DataFrame()

    last_lap = int(summary["lap"].max())
    fuel0 = fuel.fuel_remaining
    wear0 = tyre.current_wear_pct
    burn = fuel.fuel_per_lap
    wpl = tyre.wear_per_lap

    rows = []
    for i in range(horizon_laps + 1):
        lap_n = last_lap + i
        fuel_i = None if fuel0 is None or burn is None else float(fuel0 - burn * i)
        wear_i = None if wear0 is None or wpl is None else float(wear0 + wpl * i)
        rows.append(
            {
                "lap": lap_n,
                "offset": i,
                "fuel_proj": fuel_i,
                "wear_proj_pct": wear_i,
                "past_fuel_empty": bool(fuel_i is not None and fuel_i <= 0),
                "past_tyre_cliff": bool(wear_i is not None and wear_i >= tyre.cliff_wear_pct),
            }
        )
    return pd.DataFrame(rows)


@per_frame()
def analyze_stint_windows(
    df: pd.DataFrame,
    target_laps: int | None = None,
    race_distance_m: float | None = None,
    track_length_m: float | None = None,
    cliff_wear_pct: float = 55.0,
    horizon_laps: int = 15,
) -> StintWindows:
    fuel = project_fuel_window(
        df,
        target_laps=target_laps,
        race_distance_m=race_distance_m,
        track_length_m=track_length_m,
    )
    tyre = project_tyre_cliff(df, cliff_wear_pct=cliff_wear_pct)
    proj = build_window_projection(df, fuel, tyre, horizon_laps=horizon_laps)
    return StintWindows(fuel=fuel, tyre=tyre, stint_table=session_stint_table(df), projection=proj)


def stint_window_insights(
    df: pd.DataFrame,
    target_laps: int | None = None,
    race_distance_m: float | None = None,
    track_length_m: float | None = None,
    cliff_wear_pct: float = 55.0,
) -> list[StintTip]:
    """Engineer sentences for fuel window + tyre cliff."""
    tips: list[StintTip] = []
    windows = analyze_stint_windows(
        df,
        target_laps=target_laps,
        race_distance_m=race_distance_m,
        track_length_m=track_length_m,
        cliff_wear_pct=cliff_wear_pct,
    )
    fuel, tyre = windows.fuel, windows.tyre

    if fuel.fuel_remaining is not None and fuel.fuel_per_lap is not None:
        msg = (
            f"{fuel.fuel_remaining:.1f} units left · ~{fuel.fuel_per_lap:.2f}/lap → "
            f"~{fuel.laps_possible:.1f} laps in tank."
        )
        if fuel.laps_in_hand is not None and fuel.target_laps is not None:
            msg += f" Target {fuel.target_laps} laps: {fuel.laps_in_hand:+.1f} laps in hand."
            if fuel.projected_finish_fuel is not None:
                msg += f" Projected finish fuel {fuel.projected_finish_fuel:.1f}."
        sev = {"ok": "info", "tight": "tip", "short": "warning"}.get(fuel.status, "info")
        tips.append(StintTip(sev, "Fuel window", msg, "fuel"))
        if fuel.status == "short":
            tips.append(
                StintTip(
                    "warning",
                    "Fuel short to target",
                    "At current burn you will not reach the target. Add lift-coast, "
                    "shorten WOT on low-ROI zones, or lower target laps.",
                    "fuel",
                )
            )
        elif fuel.status == "tight":
            tips.append(
                StintTip(
                    "tip",
                    "Fuel margin thin",
                    "Less than ~1.5 laps spare. Copy your median-fuel management laps for the rest of the stint.",
                    "fuel",
                )
            )
    else:
        tips.append(
            StintTip(
                "info",
                "Fuel window",
                "Need fuel channel + a few laps to project remaining distance.",
                "fuel",
            )
        )

    if tyre.current_wear_pct is not None and tyre.wear_per_lap is not None:
        msg = (
            f"Wear {tyre.current_wear_pct:.0f}% · +{tyre.wear_per_lap:.1f}%/lap → "
            f"~{tyre.laps_to_cliff:.1f} laps to {tyre.cliff_wear_pct:.0f}% cliff."
        )
        if tyre.temp_avg is not None:
            msg += f" Temps {tyre.temp_avg:.0f}°C"
            if tyre.temp_trend_c_per_lap is not None:
                msg += f" ({tyre.temp_trend_c_per_lap:+.1f}/lap)."
            else:
                msg += "."
        sev = {"low": "info", "rising": "tip", "cliff": "warning"}.get(tyre.cliff_risk, "info")
        tips.append(StintTip(sev, "Tyre cliff", msg, "tyre"))
        if tyre.cliff_risk == "cliff":
            tips.append(
                StintTip(
                    "warning",
                    "Cliff window open",
                    "Grip drop is likely now — box if race strategy allows, or manage heavily "
                    "(earlier brakes, progressive exits, less mid-corner fight).",
                    "tyre",
                )
            )
        elif tyre.cliff_risk == "rising":
            tips.append(
                StintTip(
                    "tip",
                    "Cliff approaching",
                    "Reduce sliding and lockups; the next few laps decide whether you keep the stint alive.",
                    "tyre",
                )
            )
    else:
        tips.append(
            StintTip(
                "info",
                "Tyre cliff",
                "Need tyre wear samples across the current stint to project the cliff.",
                "tyre",
            )
        )

    # Cross: limiting factor
    if fuel.laps_possible is not None and tyre.laps_to_cliff is not None:
        if fuel.laps_possible < tyre.laps_to_cliff - 0.5:
            tips.append(
                StintTip(
                    "tip",
                    "Fuel limits first",
                    f"Tank (~{fuel.laps_possible:.1f} laps) empties before the tyre cliff "
                    f"(~{tyre.laps_to_cliff:.1f}). Save fuel, not just rubber.",
                    "technique",
                )
            )
        elif tyre.laps_to_cliff < fuel.laps_possible - 0.5:
            tips.append(
                StintTip(
                    "tip",
                    "Tyres limit first",
                    f"Cliff in ~{tyre.laps_to_cliff:.1f} laps while fuel allows ~{fuel.laps_possible:.1f}. "
                    "Prioritise tyre saving until the stop / finish.",
                    "technique",
                )
            )

    return tips
