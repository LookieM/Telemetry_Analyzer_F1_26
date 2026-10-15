"""
Lap-time correction shared by the live engineer and the setup duel. Pure and I/O-free.

A "group" is any set of laps driven under one condition (an engineer variant, a duel setup). This module knows
nothing about pairs, variants or garage values; callers decide which laps belong to a group.

- ``representative_laps``: drop flying-lap mistakes (> ``MISTAKE_S`` slower than the group median).
- ``fuel_fix`` / ``estimate_degradation``: fuel and tyre-age corrections.
- ``correct_groups``: corrected lap times and sector times per group, plus the degradation used.
- ``noise_estimate``: standard error of the difference of group means, floored at ``NOISE_FLOOR``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np

MISTAKE_S = 2.0
NOISE_FLOOR = 0.10
DEFAULT_DEG = 0.10


@dataclass
class Lap:
    """One completed lap as the live engine sees it. ``setup`` is the canonical garage dict."""

    lap: int
    lap_time_s: float
    valid: bool = True
    in_lap: bool = False
    out_lap: bool = False
    pit: bool = False
    s1: float | None = None
    s2: float | None = None
    s3: float | None = None
    fuel_start: float | None = None
    fuel_end: float | None = None
    compound: int | None = None
    tyre_set_idx: int | None = None
    fresh_set: bool = False
    tyre_age_laps: int = 0
    wear_max_pct: float | None = None
    wear_avg_pct: float | None = None  # mean over the four tyres (the duel's wear rate; the library uses the same)
    setup: dict[str, float] = field(default_factory=dict)
    profile: dict | None = None  # optional per-lap analysis payload; this module never looks inside

    @property
    def fuel_mid(self) -> float | None:
        if self.fuel_start is None or self.fuel_end is None:
            return None
        return (self.fuel_start + self.fuel_end) / 2.0

    @property
    def flying(self) -> bool:
        return self.valid and not (self.in_lap or self.out_lap or self.pit) and self.lap_time_s > 0

    @property
    def sectors(self) -> list[float | None]:
        return [self.s1, self.s2, self.s3]


def mistake_limit(times: Sequence[float]) -> float:
    """Slowest time still counted: the median plus ``MISTAKE_S``."""
    return float(np.median(list(times))) + MISTAKE_S


def representative_laps(laps: Sequence[Lap]) -> list[Lap]:
    """Laps of one group that are not mistakes (> ``MISTAKE_S`` slower than the group median)."""
    if not laps:
        return []
    limit = mistake_limit([x.lap_time_s for x in laps])
    return [x for x in laps if x.lap_time_s <= limit]


def fuel_fix(lap: Lap, ref_fuel: float, fuel_s_per_kg: float) -> float:
    """Seconds to subtract so ``lap`` reads as if driven with ``ref_fuel`` (0 without fuel data)."""
    return fuel_s_per_kg * (lap.fuel_mid - ref_fuel) if lap.fuel_mid is not None else 0.0


def estimate_degradation(laps: Sequence[Lap], fix: Callable[[Lap], float],
                         deg_table: Mapping[int, float] | None = None) -> tuple[float, str]:
    """Tyre degradation in s/lap and its source: "fitted" (>= 4 laps on one set over >= 3 ages), else the
    per-compound table value ("compound"), else ``DEFAULT_DEG`` ("default"). ``fix`` is the fuel correction."""
    by_set: dict[Any, list[Lap]] = {}
    for x in laps:
        by_set.setdefault(x.tyre_set_idx, []).append(x)
    best = max(by_set.values(), key=len)
    if len(best) >= 4 and len({x.tyre_age_laps for x in best}) >= 3:
        slope = float(np.polyfit([x.tyre_age_laps for x in best], [x.lap_time_s - fix(x) for x in best], 1)[0])
        return min(max(slope, 0.0), 0.6), "fitted"
    comps = [x.compound for x in laps if x.compound is not None]
    if comps:
        c = max(set(comps), key=comps.count)
        if deg_table and c in deg_table:
            return float(deg_table[c]), "compound"
    return DEFAULT_DEG, "default"


@dataclass
class Corrected:
    """Result of ``correct_groups``: per group, corrected lap times and corrected sector times (nan = missing)."""

    times: dict[str, list[float]]
    sectors: dict[str, list[list[float]]]
    deg_s_per_lap: float
    deg_source: str

    @property
    def means(self) -> dict[str, float]:
        return {k: float(np.mean(v)) for k, v in self.times.items()}


def correct_groups(groups: Mapping[str, Sequence[Lap]], fuel_s_per_kg: float,
                   deg_table: Mapping[int, float] | None = None) -> Corrected:
    """Correct every lap of every group to the mean fuel load and tyre age of all the laps together.

    ``groups`` should already hold representative laps (see ``representative_laps``) and be non-empty."""
    allp = [x for laps in groups.values() for x in laps]
    mids = [x.fuel_mid for x in allp if x.fuel_mid is not None]
    ref_fuel = float(np.mean(mids)) if mids else 0.0
    ref_age = float(np.mean([x.tyre_age_laps for x in allp]))

    def fix_fuel(x: Lap) -> float:
        return fuel_fix(x, ref_fuel, fuel_s_per_kg)

    deg, src = estimate_degradation(allp, fix_fuel, deg_table)
    times: dict[str, list[float]] = {k: [] for k in groups}
    sect: dict[str, list[list[float]]] = {k: [] for k in groups}
    for k, laps in groups.items():
        for x in laps:
            fix = fix_fuel(x) + deg * (x.tyre_age_laps - ref_age)
            times[k].append(x.lap_time_s - fix)
            sect[k].append([(s - fix * s / x.lap_time_s) if s is not None else math.nan for s in x.sectors])
    return Corrected(times, sect, deg, src)


def noise_estimate(times: Mapping[str, Sequence[float]]) -> float:
    """Standard error of the difference between group means (sum of per-group variance / n), at least
    ``NOISE_FLOOR`` seconds."""
    var = sum((float(np.std(v, ddof=1)) if len(v) > 1 else 0.0) ** 2 / len(v) for v in times.values())
    return max(NOISE_FLOOR, math.sqrt(var))
