"""Coaching-style insights derived from telemetry."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import align_laps, compute_time_delta, get_lap


@dataclass
class Insight:
    severity: str  # info | tip | warning
    title: str
    detail: str
    category: str


def _pct(x: float) -> str:
    return f"{x:.1f}%"


def _brake_onsets(
    dist: np.ndarray,
    brake: np.ndarray,
    speed: np.ndarray,
    *,
    brake_on: float = 0.40,
    brake_off: float = 0.18,
    min_approach_speed: float = 160.0,
    min_gap_m: float = 70.0,
) -> list[dict[str, float]]:
    """
    Detect heavy brake markers after a high-speed approach.

    Each event: onset distance, peak-brake distance, peak pressure, approach speed.
    """
    if len(dist) < 5 or len(brake) != len(dist):
        return []
    events: list[dict[str, float]] = []
    i = 1
    n = len(dist)
    while i < n:
        if brake[i] >= brake_on and brake[i - 1] < brake_off:
            # Approach speed: max in the ~120 m before onset
            d0 = float(dist[i])
            pre = (dist >= d0 - 120.0) & (dist < d0)
            if pre.any():
                approach = float(np.nanmax(speed[pre])) if len(speed) == n else float("nan")
            else:
                approach = float(speed[i]) if len(speed) == n else float("nan")
            if not np.isfinite(approach) or approach < min_approach_speed:
                i += 1
                continue
            # Peak within this braking zone until release
            j = i
            peak_i = i
            while j < n and not (brake[j] < brake_off and j > i + 2):
                if brake[j] > brake[peak_i]:
                    peak_i = j
                # End event if we've travelled far with low brake
                if dist[j] - d0 > 250:
                    break
                j += 1
            if events and d0 - events[-1]["onset_m"] < min_gap_m:
                i = max(i + 1, j)
                continue
            events.append(
                {
                    "onset_m": d0,
                    "peak_m": float(dist[peak_i]),
                    "peak_brake": float(brake[peak_i]),
                    "approach_speed": approach,
                }
            )
            i = max(i + 1, j)
            continue
        i += 1
    return events


def compare_brake_markers(
    aligned: pd.DataFrame,
    *,
    match_radius_m: float = 90.0,
    flag_m: float = 8.0,
) -> list[dict]:
    """
    Match focus vs reference brake onsets on an aligned lap.

    Returns list of dicts with onset distances and delta_m (focus − ref;
    positive = focus brakes later).
    """
    need = ["lap_distance", "ref_brake", "cmp_brake", "ref_speed", "cmp_speed"]
    if aligned.empty or any(c not in aligned.columns for c in need):
        return []
    dist = aligned["lap_distance"].to_numpy(dtype=float)
    ref_ev = _brake_onsets(dist, aligned["ref_brake"].to_numpy(dtype=float), aligned["ref_speed"].to_numpy(dtype=float))
    cmp_ev = _brake_onsets(dist, aligned["cmp_brake"].to_numpy(dtype=float), aligned["cmp_speed"].to_numpy(dtype=float))
    if not ref_ev or not cmp_ev:
        return []

    used_ref: set[int] = set()
    matched: list[dict] = []
    for ce in cmp_ev:
        best_i = None
        best_abs = match_radius_m + 1.0
        for ri, re in enumerate(ref_ev):
            if ri in used_ref:
                continue
            gap = abs(ce["onset_m"] - re["onset_m"])
            if gap < best_abs:
                best_abs = gap
                best_i = ri
        if best_i is None or best_abs > match_radius_m:
            continue
        used_ref.add(best_i)
        re = ref_ev[best_i]
        delta_m = float(ce["onset_m"] - re["onset_m"])
        delta_peak_m = float(ce["peak_m"] - re["peak_m"])
        matched.append(
            {
                "cmp_onset_m": ce["onset_m"],
                "ref_onset_m": re["onset_m"],
                "delta_m": delta_m,
                "delta_peak_m": delta_peak_m,
                "cmp_peak_m": ce["peak_m"],
                "ref_peak_m": re["peak_m"],
                "approach_speed": ce["approach_speed"],
                "flagged": abs(delta_m) >= flag_m,
            }
        )
    return matched


def _brake_marker_insights(
    aligned: pd.DataFrame,
    reference_lap: int,
    *,
    track: str | None = None,
    track_length: float | None = None,
    focus_df: pd.DataFrame | None = None,
    ref_df: pd.DataFrame | None = None,
) -> list[Insight]:
    """Per-marker early/late brake callouts; enrich with corner names when possible."""
    matched = compare_brake_markers(aligned)
    if not matched:
        return []

    corner_lookup = None
    if track is not None or (focus_df is not None and ref_df is not None):
        try:
            from .corners import analyze_lap_corners, compare_corners, resolve_corners

            corners = resolve_corners(track, track_length, focus_df if focus_df is not None else ref_df)
            if corners and focus_df is not None and ref_df is not None:
                fc = analyze_lap_corners(focus_df, track, track_length, corners=corners)
                rc = analyze_lap_corners(ref_df, track, track_length, corners=corners)
                cmp = compare_corners(fc, rc)
                if not cmp.empty and "delta_brake_point_m" in cmp.columns:
                    corner_lookup = cmp
        except Exception:
            corner_lookup = None

    insights: list[Insight] = []
    flagged = [m for m in matched if m["flagged"]]
    if not flagged:
        return insights

    # Prefer largest |delta| markers (up to 3)
    flagged = sorted(flagged, key=lambda m: abs(m["delta_m"]), reverse=True)[:3]
    early = [m for m in flagged if m["delta_m"] < 0]
    late = [m for m in flagged if m["delta_m"] > 0]

    def _name_near(dist_m: float) -> str:
        if corner_lookup is not None and "start_m" in corner_lookup.columns:
            hit = corner_lookup[
                (corner_lookup["start_m"] - 100 <= dist_m) & (corner_lookup["end_m"] + 20 >= dist_m)
            ]
            if not hit.empty:
                # Prefer corner rows with a brake delta
                row = hit.iloc[0]
                return str(row.get("corner_name") or row.get("corner_id") or f"{dist_m:.0f} m")
        return f"{dist_m:.0f} m"

    for m in early[:2]:
        insights.append(
            Insight(
                "tip",
                f"Early brake - {_name_near(m['cmp_onset_m'])}",
                f"You brake {abs(m['delta_m']):.0f} m earlier than lap {reference_lap} "
                f"(focus {m['cmp_onset_m']:.0f} m vs ref {m['ref_onset_m']:.0f} m, "
                f"approach ~{m['approach_speed']:.0f} km/h). Try a later marker if the car still stops.",
                "braking",
            )
        )
    for m in late[:2]:
        insights.append(
            Insight(
                "info" if m["delta_m"] < 15 else "tip",
                f"Later brake - {_name_near(m['cmp_onset_m'])}",
                f"You brake {m['delta_m']:.0f} m later than lap {reference_lap} "
                f"(focus {m['cmp_onset_m']:.0f} m vs ref {m['ref_onset_m']:.0f} m). "
                "Good aggression — watch lock-ups and turn-in stability.",
                "braking",
            )
        )

    # Corner-table brake deltas when available (named corners)
    if corner_lookup is not None and "delta_brake_point_m" in corner_lookup.columns:
        crows = corner_lookup.copy()
        if "kind" in crows.columns:
            crows = crows[crows["kind"] == "corner"]
        crows = crows[crows["delta_brake_point_m"].notna()]
        crows = crows[crows["delta_brake_point_m"].abs() >= 8]
        crows = crows.assign(_abs_dbp=crows["delta_brake_point_m"].abs()).sort_values(
            "_abs_dbp", ascending=False
        ).head(2)
        for _, row in crows.iterrows():
            d = float(row["delta_brake_point_m"])
            name = str(row.get("corner_name") or row["corner_id"])
            title_key = f"Brake marker - {name}"
            if any(ins.title == title_key for ins in insights):
                continue
            if d < 0:
                insights.append(
                    Insight(
                        "tip",
                        title_key,
                        f"{name}: brake point {abs(d):.0f} m earlier than reference "
                        f"({row['brake_point_m']:.0f} m vs {row.get('ref_brake_point_m', float('nan')):.0f} m).",
                        "braking",
                    )
                )
            else:
                insights.append(
                    Insight(
                        "info",
                        title_key,
                        f"{name}: brake point {d:.0f} m later than reference "
                        f"({row['brake_point_m']:.0f} m vs {row.get('ref_brake_point_m', float('nan')):.0f} m).",
                        "braking",
                    )
                )
    return insights


def generate_insights(
    df: pd.DataFrame,
    lap: int,
    reference_lap: int | None = None,
    track: str | None = None,
    track_length: float | None = None,
) -> list[Insight]:
    """Return human-readable coaching notes for a lap (optionally vs reference)."""
    insights: list[Insight] = []
    lap_df = get_lap(df, lap)
    if lap_df.empty:
        return [
            Insight("warning", "No data", f"Lap {lap} has no samples.", "data")
        ]

    # --- Single-lap technique ---
    if "coasting" in lap_df.columns and "speed" in lap_df.columns:
        coast_fast = lap_df["coasting"] & (lap_df["speed"] > 120)
        coast_pct = float(coast_fast.mean() * 100)
        if coast_pct > 4:
            insights.append(
                Insight(
                    "tip",
                    "Coasting while fast",
                    f"About {_pct(coast_pct)} of the lap is neither throttle nor brake above 120 km/h. "
                    "Shorten lift-coast or commit earlier to brake/throttle.",
                    "inputs",
                )
            )

    if "throttle" in lap_df.columns:
        partial = (lap_df["throttle"] > 0.15) & (lap_df["throttle"] < 0.85)
        if "brake" in lap_df.columns:
            partial = partial & (lap_df["brake"] < 0.05)
        partial_pct = float(partial.mean() * 100)
        if partial_pct > 12:
            insights.append(
                Insight(
                    "tip",
                    "Lots of partial throttle",
                    f"{_pct(partial_pct)} of the lap is mid-throttle. "
                    "Often means hesitation on exit — try earlier, progressive application.",
                    "inputs",
                )
            )
        full_pct = float((lap_df["throttle"] > 0.98).mean() * 100)
        insights.append(
            Insight(
                "info",
                "Full throttle share",
                f"You spent {_pct(full_pct)} of the lap at full throttle.",
                "inputs",
            )
        )

    if "lockup_risk" in lap_df.columns:
        locks = int(lap_df["lockup_risk"].sum())
        if locks > 15:
            insights.append(
                Insight(
                    "warning",
                    "Possible lock-ups",
                    f"Detected ~{locks} samples with high wheel slip under braking. "
                    "Ease initial brake pressure or move bias rearward slightly.",
                    "braking",
                )
            )

    if all(f"tyre_temp_{i}" in lap_df.columns for i in range(4)):
        temps = [lap_df[f"tyre_temp_{i}"].mean() for i in range(4)]
        labels = ["RL", "RR", "FL", "FR"]
        avg = float(np.mean(temps))
        spread = float(np.max(temps) - np.min(temps))
        hottest = labels[int(np.argmax(temps))]
        coldest = labels[int(np.argmin(temps))]
        insights.append(
            Insight(
                "info",
                "Tyre temperatures",
                f"Avg {avg:.0f}°C, spread {spread:.0f}°C ({hottest} hottest, {coldest} coldest).",
                "tyres",
            )
        )
        if spread > 15:
            insights.append(
                Insight(
                    "tip",
                    "Tyre temp imbalance",
                    f"{hottest} is much hotter than {coldest}. Check camber/pressure/toe or driving style (one-sided load).",
                    "tyres",
                )
            )

    if all(f"tyre_wear_{i}" in lap_df.columns for i in range(4)):
        wears = [float(lap_df[f"tyre_wear_{i}"].iloc[-1]) * 100 for i in range(4)]
        insights.append(
            Insight(
                "info",
                "Tyre wear (end of lap)",
                " / ".join(f"{lab} {w:.1f}%" for lab, w in zip(["RL", "RR", "FL", "FR"], wears)),
                "tyres",
            )
        )

    if "ers_store_mj" in lap_df.columns:
        start = float(lap_df["ers_store_mj"].iloc[0])
        end = float(lap_df["ers_store_mj"].iloc[-1])
        insights.append(
            Insight(
                "info",
                "ERS battery",
                f"Started {start:.2f} MJ → finished {end:.2f} MJ (Δ {end - start:+.2f} MJ).",
                "ers",
            )
        )

    if "fuel" in lap_df.columns:
        used = float(lap_df["fuel"].iloc[0] - lap_df["fuel"].iloc[-1])
        insights.append(
            Insight(
                "info",
                "Fuel used",
                f"{used:.2f} units this lap (start {lap_df['fuel'].iloc[0]:.2f}).",
                "fuel",
            )
        )

    # --- Vs reference ---
    if reference_lap is not None and reference_lap != lap:
        ref = get_lap(df, reference_lap)
        if not ref.empty:
            aligned = compute_time_delta(align_laps(ref, lap_df))
            if not aligned.empty and "delta_time" in aligned.columns:
                final = float(aligned["delta_time"].iloc[-1])
                worst_i = int(aligned["delta_gain"].idxmin()) if "delta_gain" in aligned.columns else None
                best_i = int(aligned["delta_gain"].idxmax()) if "delta_gain" in aligned.columns else None

                verb = "slower" if final > 0 else "faster"
                insights.append(
                    Insight(
                        "info" if abs(final) < 0.15 else "tip",
                        f"Vs lap {reference_lap}",
                        f"Lap {lap} is {abs(final):.3f}s {verb} overall.",
                        "delta",
                    )
                )

                if worst_i is not None and "lap_distance" in aligned.columns:
                    dist = float(aligned.loc[worst_i, "lap_distance"])
                    loss = float(aligned.loc[worst_i, "delta_gain"])
                    if loss < -0.02:
                        # Check braking nearby
                        detail = f"Biggest instant loss near {dist:.0f} m."
                        if "ref_brake" in aligned.columns and "cmp_brake" in aligned.columns:
                            window = aligned.iloc[max(0, worst_i - 20) : worst_i + 20]
                            if window["cmp_brake"].max() > 0.2 and window["cmp_brake"].idxmax() < window["ref_brake"].idxmax():
                                detail += " You appear to brake earlier than the reference."
                            elif window["cmp_speed"].min() < window["ref_speed"].min() - 3:
                                detail += " Minimum corner speed is lower than reference."
                        insights.append(
                            Insight("tip", "Biggest time loss zone", detail, "delta")
                        )

                if best_i is not None and "lap_distance" in aligned.columns:
                    dist = float(aligned.loc[best_i, "lap_distance"])
                    gain = float(aligned.loc[best_i, "delta_gain"])
                    if gain > 0.02:
                        insights.append(
                            Insight(
                                "info",
                                "Biggest time gain zone",
                                f"You gain most near {dist:.0f} m vs lap {reference_lap}.",
                                "delta",
                            )
                        )

                # Brake markers: onset / peak vs reference (per event, optionally named corners)
                if all(c in aligned.columns for c in ["ref_brake", "cmp_brake", "ref_speed", "cmp_speed", "lap_distance"]):
                    insights.extend(
                        _brake_marker_insights(
                            aligned,
                            reference_lap,
                            track=track,
                            track_length=track_length,
                            focus_df=lap_df,
                            ref_df=ref,
                        )
                    )

    if not insights:
        insights.append(
            Insight("info", "Looking clean", "No strong red flags on this lap from the heuristics.", "general")
        )

    # Deduplicate by title
    seen = set()
    unique = []
    for item in insights:
        if item.title not in seen:
            seen.add(item.title)
            unique.append(item)
    return unique
