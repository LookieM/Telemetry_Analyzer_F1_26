"""
Setup-duel ranking (pure, I/O-free): rank 2-3 contestants by a race-time estimate per lap.

score_s = 0.7 * (race pace + wear cost) + 0.3 * one-lap pace, all in seconds per lap (lower is better).

- race pace: mean of the contestant's corrected clean laps; one-lap pace: its best corrected lap.
- wear cost: what the contestant's tyre wear rate costs over a race, relative to the contestant that wears least.
  ``plan_time(wear_pct_per_lap)`` (the strategy model, see ``duel_library.wear_plan_time``) gives the best plan
  race time for a wear rate; without it the cost falls back to ``FALLBACK_S_PER_PCT_LAP`` per extra %/lap.
- noise band: differences of the score inside it are "no measurable difference"; the order inside such a cluster
  is decided by balance (distance from neutral per phase), then by feel (when given), else left undecided.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

from telemetry.corner_balance import PHASES, balance_label, relative_index

from .live.lap_correction import noise_estimate

W_RACE = 0.7
W_QUALI = 0.3
# Seconds per lap for every extra %/lap of tyre wear when the strategy model is not available. A setup that wears
# 0.5 %/lap more also loses grip faster (about +0.04 s/lap of degradation, a mean tyre age of ~12 laps) and
# triggers stops: roughly 0.5 s per lap over a 50 % race.
FALLBACK_S_PER_PCT_LAP = 0.5
# Mean distance from neutral (deg, summed over the three phases) that must separate two setups for balance to decide.
BALANCE_MARGIN_DEG = 0.5
WEAR_CALLOUT_PCT = 0.3
# Noise band (s per lap) when the contestants' laps come from different sessions: track evolution and temperature
# are not corrected, so a gap smaller than this is not trusted.
CROSS_SESSION_NOISE_S = 0.5


@dataclass
class Contestant:
    key: str
    name: str
    times: list[float]  # corrected clean lap times
    wear_pct_per_lap: float | None = None
    balance: dict[str, float | None] | None = None  # raw understeer index (deg) per phase; None = not measured
    sessions: list[int] = field(default_factory=list)  # ids of the sessions the counted laps came from ([] = unknown)
    extra: dict[str, Any] = field(default_factory=dict)  # passed through to the output

    @property
    def n_laps(self) -> int:
        return len(self.times)


def balance_block(balance: dict[str, float | None] | None) -> dict[str, Any] | None:
    """Per phase {deg, relative, label} plus the distance from neutral (sum of |relative index|)."""
    if not balance:
        return None
    out: dict[str, Any] = {}
    dist, seen = 0.0, 0
    for p in PHASES:
        raw = balance.get(p)
        rel = relative_index(raw, p)
        out[p] = {"deg": raw, "relative": rel, "label": balance_label(raw, p)}
        if rel is not None:
            dist += abs(rel)
            seen += 1
    out["distance"] = dist if seen else None
    return out


def _wear_costs(cs: Sequence[Contestant], plan_time: Callable[[float], float | None] | None,
                race_laps: int | None) -> tuple[dict[str, float], str, str]:
    """(cost per lap per contestant key, source "model" | "fallback" | "none", note)."""
    wears = {c.key: c.wear_pct_per_lap for c in cs if c.wear_pct_per_lap is not None}
    if not wears:
        return {c.key: 0.0 for c in cs}, "none", "No tyre wear was measured, so wear is not part of the ranking."
    fill = float(np.median(list(wears.values())))
    full = {c.key: wears.get(c.key, fill) for c in cs}
    note = ""
    if len(wears) < len(cs):
        note = "Wear is missing for some contestants (too few laps); the median of the others was used. "
    if plan_time is not None and race_laps:
        try:
            times: dict[str, float | None] = {k: plan_time(w) for k, w in full.items()}
        except Exception:  # a broken model must not block the ranking
            times = {k: None for k in full}
        if all(t is not None for t in times.values()):
            best = min(t for t in times.values() if t is not None)
            costs = {k: (t - best) / race_laps for k, t in times.items() if t is not None}
            return costs, "model", note + "Wear cost from the strategy model (50 % race)."
        note += "The strategy model has no feasible plan for these wear rates. "
    else:
        note += "No tyre model for this track. "
    lo = min(full.values())
    return ({k: (w - lo) * FALLBACK_S_PER_PCT_LAP for k, w in full.items()}, "fallback",
            note + f"Wear cost is a fixed estimate ({FALLBACK_S_PER_PCT_LAP:.2f} s per lap for every extra %/lap), not from the strategy model.")


def _clusters(items: list[dict[str, Any]], noise: float) -> list[list[dict[str, Any]]]:
    """Score-sorted items split where the gap to the previous one exceeds the noise band."""
    out: list[list[dict[str, Any]]] = []
    for it in items:
        if out and it["score_s"] - out[-1][-1]["score_s"] <= noise:
            out[-1].append(it)
        else:
            out.append([it])
    return out


def _break_tie(cluster: list[dict[str, Any]], feel: dict[str, int] | None) -> tuple[list[dict[str, Any]], str]:
    dists = [it["balance"]["distance"] if it["balance"] else None for it in cluster]
    if all(d is not None for d in dists) and max(dists) - min(dists) > BALANCE_MARGIN_DEG:
        return sorted(cluster, key=lambda it: it["balance"]["distance"]), "balance"
    if feel and all(it["key"] in feel for it in cluster):
        return sorted(cluster, key=lambda it: feel[it["key"]]), "feel"
    return cluster, "none"


def rank_contestants(
    contestants: Sequence[Contestant],
    *,
    plan_time: Callable[[float], float | None] | None = None,
    race_laps: int | None = None,
    feel_order: Sequence[str] | None = None,
    noise_s: float | None = None,
) -> dict[str, Any]:
    """Rank contestants (see module doc). ``feel_order`` = keys, best first (live duels only)."""
    cs = list(contestants)
    if len(cs) < 2:
        raise ValueError("A duel needs at least two contestants")
    if any(c.n_laps == 0 for c in cs):
        raise ValueError("Every contestant needs at least one lap")
    noise = noise_s if noise_s is not None else noise_estimate({c.key: c.times for c in cs})
    known = all(c.sessions for c in cs)
    same_session = (not known) or bool(set.intersection(*(set(c.sessions) for c in cs)))
    if not same_session:
        noise = max(noise, CROSS_SESSION_NOISE_S)
    cost, cost_source, cost_note = _wear_costs(cs, plan_time, race_laps)
    feel = {k: i for i, k in enumerate(feel_order)} if feel_order else None

    items: list[dict[str, Any]] = []
    for c in cs:
        race, quali = float(np.mean(c.times)), float(np.min(c.times))
        items.append({
            "key": c.key, "name": c.name, "n_laps": c.n_laps,
            "race_pace_s": race, "quali_pace_s": quali,
            "wear_pct_per_lap": c.wear_pct_per_lap, "race_cost_s": cost[c.key],
            "score_s": W_RACE * (race + cost[c.key]) + W_QUALI * quali,
            "balance": balance_block(c.balance),
            "sessions": sorted(c.sessions),
            **c.extra,
        })
    items.sort(key=lambda it: it["score_s"])
    ordered: list[dict[str, Any]] = []
    methods: list[str] = []
    callouts: list[str] = []
    if not same_session:
        by_sessions = " vs ".join(", ".join(f"#{s}" for s in sorted(c.sessions)) for c in cs)
        callouts.append(f"Laps come from different sessions ({by_sessions}): track evolution and temperature are not corrected, treat the gap with caution.")
    for cl in _clusters(items, noise):
        if len(cl) == 1:
            ordered += cl
            methods.append("stopwatch")
            continue
        res, method = _break_tie(cl, feel)
        gap = cl[-1]["score_s"] - cl[0]["score_s"]
        callouts.append(
            f"{' and '.join(it['name'] for it in cl)} are within the noise ({gap:.3f} s per lap, band {noise:.2f} s): "
            + {"balance": "balance decides.", "feel": "your feel decides.", "none": "no measurable difference."}[method]
        )
        ordered += res
        methods.append(method)
    winner = ordered[0]
    tie_break = methods[0]  # clusters are score-ordered, so the winner sits in the first one
    best_score = min(it["score_s"] for it in items)
    for rank, it in enumerate(ordered, 1):
        it["rank"] = rank
        it["delta_s"] = it["score_s"] - best_score

    pairs = []
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            gap = abs(a["score_s"] - b["score_s"])
            pairs.append({"a": a["key"], "b": b["key"], "gap_s": gap, "measurable": gap > noise})

    fastest_lap = min(items, key=lambda it: it["quali_pace_s"])
    best_race = min(items, key=lambda it: it["race_pace_s"] + it["race_cost_s"])
    if fastest_lap["key"] != best_race["key"] and abs(fastest_lap["quali_pace_s"] - best_race["quali_pace_s"]) > noise:
        callouts.append(f"{fastest_lap['name']} has the fastest single lap, but {best_race['name']} is better over a race distance.")
    wears = [it for it in items if it["wear_pct_per_lap"] is not None]
    if len(wears) >= 2:
        gentle = min(wears, key=lambda it: it["wear_pct_per_lap"])
        harsh = max(wears, key=lambda it: it["wear_pct_per_lap"])
        if harsh["wear_pct_per_lap"] - gentle["wear_pct_per_lap"] >= WEAR_CALLOUT_PCT and gentle is not winner:
            callouts.append(
                f"{gentle['name']} is the gentlest on the tyres ({gentle['wear_pct_per_lap']:.2f} vs "
                f"{harsh['wear_pct_per_lap']:.2f} % per lap on {harsh['name']})."
            )
    if feel and feel_order and feel_order[0] in feel and feel_order[0] != winner["key"]:
        top = next(it for it in ordered if it["key"] == feel_order[0])
        callouts.append(f"You rated {top['name']} first, but the ranking puts {winner['name']} first: you decide.")
    if tie_break == "none":
        callouts.append("No measurable difference between the leading setups: choose by feel.")

    return {
        "contestants": ordered,
        "order": [it["key"] for it in ordered],
        "winner": winner["key"],
        "tie_break": tie_break,
        "decided": tie_break != "none",
        "same_session": same_session,
        "noise_s": noise,
        "pairs": pairs,
        "weights": {"race": W_RACE, "quali": W_QUALI},
        "cost_source": cost_source,
        "cost_note": cost_note.strip(),
        "callouts": callouts,
    }
