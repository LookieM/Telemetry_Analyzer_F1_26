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


def generate_insights(
    df: pd.DataFrame,
    lap: int,
    reference_lap: int | None = None,
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

                # Brake point comparison: first heavy brake after high speed
                if all(c in aligned.columns for c in ["ref_brake", "cmp_brake", "ref_speed", "lap_distance"]):
                    for label, brake_col in (("ref", "ref_brake"), ("cmp", "cmp_brake")):
                        pass
                    # Find zones where speed > 200 then brake > 0.4
                    heavy = aligned["cmp_brake"] > 0.45
                    ref_heavy = aligned["ref_brake"] > 0.45
                    if heavy.any() and ref_heavy.any():
                        # Approximate: compare distance of first heavy brake in last third of high-speed approaches
                        # Simpler metric: average distance where brake crosses 0.4 while decelerating
                        cmp_on = aligned.loc[(aligned["cmp_brake"] > 0.4) & (aligned["ref_speed"] > 180), "lap_distance"]
                        ref_on = aligned.loc[(aligned["ref_brake"] > 0.4) & (aligned["ref_speed"] > 180), "lap_distance"]
                        if len(cmp_on) and len(ref_on):
                            # Use early samples of each braking event groups — crude: median of first 5% of brake points
                            early_cmp = float(cmp_on.iloc[: max(1, len(cmp_on) // 20)].mean())
                            early_ref = float(ref_on.iloc[: max(1, len(ref_on) // 20)].mean())
                            # Not very reliable globally; instead count samples where cmp brakes while ref still full throttle
                            early_brake = (
                                (aligned["cmp_brake"] > 0.3)
                                & (aligned["ref_throttle"] > 0.9)
                                & (aligned["ref_speed"] > 150)
                            )
                            late_brake = (
                                (aligned["ref_brake"] > 0.3)
                                & (aligned["cmp_throttle"] > 0.9)
                                & (aligned["cmp_speed"] > 150)
                            )
                            if early_brake.sum() > 25:
                                insights.append(
                                    Insight(
                                        "tip",
                                        "Earlier braking than reference",
                                        "Multiple zones where you brake while the reference is still flat out. "
                                        "Try later braking points on those approaches.",
                                        "braking",
                                    )
                                )
                            elif late_brake.sum() > 25:
                                insights.append(
                                    Insight(
                                        "info",
                                        "Later braking than reference",
                                        "You often stay flat longer than the reference — good aggression, watch lock-ups.",
                                        "braking",
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
