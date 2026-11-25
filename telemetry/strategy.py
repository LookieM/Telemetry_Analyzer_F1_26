"""
Race strategy: lap-time model, stop / compound optimisation, pit windows, undercut and
safety-car calls, and a post-race review against the optimum.

Lap time on lap i (0-based) of a stint on compound c at tyre age a:
    base + offset_c + deg_c * a + deg2_c * a^2 + warmup_c * [a == 0] + k_fuel * (fuel_i - 5 kg)
Each stop adds the pit loss. A stint may not run past the wear limit.
Stint costs are additive and order-free, so a plan is a multiset of (compound, stint length).

With a tyre-set inventory ({compound: [wear % of each set you have]}) a compound runs at most as
many stints as you have sets of it, the freshest first, and a used set starts its stint at the
equivalent age wear / wear-rate (slower, fewer laps to the wear limit). Without one every stint
is on a new set and the sets are unlimited.
"""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .compounds import Allocation, c_label, is_slick, softness
from .corners import normalize_track_name
from .db import connect
from .metrics import FUEL_S_PER_KG
from .track_catalog import DEFAULT_PIT_LOSS_S, PIT_LOSS_FALLBACK_S, RACE_LAPS_FULL
from .tyres import WEAR_LIMIT_PCT, TrackTyreModel, default_wear_limit, tyre_stints

INF = float("inf")
FUEL_REF_KG = 5.0  # base pace and corrected lap times are expressed at this fuel load
DEFAULT_RACE_SHARE = 0.5  # game races in the library are 50% distance

OVERRIDES_SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_overrides (
    track TEXT NOT NULL,
    state TEXT NOT NULL,
    params_json TEXT,
    compounds_json TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (track, state)
);
"""


@dataclass
class CompoundSpec:
    code: int
    label: str
    color: str
    offset_s: float
    deg_s_per_lap: float
    wear_pct_per_lap: float | None
    warmup_s: float = 0.0
    deg2_s: float = 0.0
    source: str = "measured"
    use: bool = True

    def max_laps(self, wear_limit: float, race_laps: int, start_wear: float = 0.0) -> int:
        """Laps to the wear limit; a used set (``start_wear`` %) has fewer, 0 when already past it."""
        if not self.wear_pct_per_lap or self.wear_pct_per_lap <= 1e-6:
            return race_laps
        if start_wear <= 0:
            return max(1, min(race_laps, int(wear_limit / self.wear_pct_per_lap)))
        return max(0, min(race_laps, int((wear_limit - start_wear) / self.wear_pct_per_lap + 1e-9)))

    def start_age(self, wear: float) -> float:
        """Equivalent tyre age (laps) of a set already worn ``wear`` %."""
        if wear <= 0 or not self.wear_pct_per_lap or self.wear_pct_per_lap <= 1e-6:
            return 0.0
        return float(wear) / self.wear_pct_per_lap

    def lap_deltas(self, n: int, start_age: float = 0.0) -> np.ndarray:
        """Time over base pace for tyre ages start..start+n-1 (warm-up on the first lap)."""
        a = float(start_age) + np.arange(n, dtype=float)
        out = self.offset_s + self.deg_s_per_lap * a + self.deg2_s * a**2
        if n:
            out[0] += self.warmup_s
        return out


@dataclass
class RaceParams:
    laps: int
    pit_loss_s: float
    base_pace_s: float = 90.0
    fuel_per_lap_kg: float = 1.0
    fuel_effect_s_per_kg: float = FUEL_S_PER_KG
    fuel_margin_laps: float = 1.0
    wear_limit_pct: float = WEAR_LIMIT_PCT
    sc_pit_factor: float = 0.55
    require_two_compounds: bool = True
    max_stops: int = 3
    window_tolerance_s: float = 2.0

    @property
    def start_fuel_kg(self) -> float:
        return (self.laps + self.fuel_margin_laps) * self.fuel_per_lap_kg

    def fuel_times(self) -> np.ndarray:
        """Fuel effect per lap vs the 5 kg reference (identical for every plan)."""
        fuel = self.start_fuel_kg - self.fuel_per_lap_kg * np.arange(self.laps, dtype=float)
        return self.fuel_effect_s_per_kg * (fuel - FUEL_REF_KG)


@dataclass
class Plan:
    compounds: tuple[int, ...]
    stints: tuple[int, ...]
    race_time: float
    windows: list[tuple[int, int]] = field(default_factory=list)
    start_wear: tuple[float, ...] = ()  # wear % of each stint's set at fitting (empty = all new)

    @property
    def stops(self) -> int:
        return len(self.stints) - 1

    @property
    def stop_laps(self) -> list[int]:
        """Box at the end of these laps (1-based lap counts)."""
        return [int(x) for x in np.cumsum(self.stints)[:-1]]

    def wears(self) -> tuple[float, ...]:
        return self.start_wear or tuple(0.0 for _ in self.compounds)

    def describe(self, specs: dict[int, CompoundSpec]) -> str:
        return " → ".join(f"{_short(specs, c)}{_used(w)} {n}" for c, n, w in zip(self.compounds, self.stints, self.wears()))


def _used(wear: float | None) -> str:
    return f" (used {wear:.0f}%)" if wear is not None and wear >= 0.5 else ""


def _short(specs: dict[int, CompoundSpec], code: int) -> str:
    spec = specs.get(code)
    return spec.label if spec else str(code)


# --------------------------------------------------------------------------- model inputs


def specs_from_model(model: TrackTyreModel) -> list[CompoundSpec]:
    return [
        CompoundSpec(
            code=m.code,
            label=m.label,
            color=m.color,
            offset_s=m.offset_s,
            deg_s_per_lap=m.deg_s_per_lap,
            wear_pct_per_lap=m.wear_pct_per_lap,
            warmup_s=m.warmup_s,
            source=m.source,
        )
        for m in model.compounds.values()
    ]


def default_params(model: TrackTyreModel, track: str | None = None) -> RaceParams:
    track_n = normalize_track_name(track or model.track) or (track or model.track)
    full = RACE_LAPS_FULL.get(track_n)
    # Races are always 50% distance: the catalog lap count is exact; a library export can be cut short.
    laps = math.ceil(full * DEFAULT_RACE_SHARE) if full else (model.race_laps_seen or 30)
    pit = model.pit_loss or PIT_LOSS_FALLBACK_S.get(track_n, DEFAULT_PIT_LOSS_S)
    stats = model.stats
    return RaceParams(
        laps=int(laps),
        pit_loss_s=float(pit),
        base_pace_s=float(model.base_pace_s) if model.base_pace_s else 90.0,
        fuel_per_lap_kg=float(model.fuel_per_lap) if model.fuel_per_lap else 1.1,
        # Must match the correction the model's lap times were built with.
        fuel_effect_s_per_kg=stats.fuel_s_per_kg if stats else FUEL_S_PER_KG,
        wear_limit_pct=default_wear_limit(stats),
        require_two_compounds=model.state == "dry",
        sc_pit_factor=model.sc_pit_factor or RaceParams.sc_pit_factor,
    )


# Placeholder model for a track with no long runs yet (one softness step apart; edit before use).
_MANUAL = {"S": (-0.5, 0.25, 6.0), "M": (0.0, 0.15, 4.5), "H": (0.45, 0.09, 3.0)}


GAME_LIFE_LAPS_TOLERANCE = 0.15  # game usable life is only used when captured at (about) this race length


def manual_specs(
    alloc: Allocation,
    game: dict[str, Any] | None = None,
    *,
    laps: int | None = None,
    wear_limit: float | None = None,
) -> list[CompoundSpec]:
    """Compound model for a track the library has no long runs on.

    With ``game`` (compounds.get_game_tyres: what the TyreSets packet reported on this track) the
    pace offsets come from the game's own lap-time deltas between compounds, and the wear rate from
    its recommended usable life when that was captured at the same race length. Degradation stays
    a generic placeholder until you have long runs on the track.
    """
    gc = (game or {}).get("compounds") or {}
    by_role = {v.get("role"): v for v in gc.values()}
    ref = by_role.get("M")
    life_ok = bool(game and game.get("total_laps") and laps
                   and abs(int(game["total_laps"]) - int(laps)) <= GAME_LIFE_LAPS_TOLERANCE * int(laps))
    out = []
    for code, role in sorted(alloc.roles.items(), key=lambda kv: -softness(kv[0])):
        if role not in _MANUAL:
            continue
        off, deg, wear = _MANUAL[role]
        src = "manual · fill in"
        g = gc.get(int(code))
        if g and ref is not None:
            off = (int(g["delta_ms"]) - int(ref["delta_ms"])) / 1000.0
            src = "game pace offset · deg generic"
            if life_ok and wear_limit and int(g.get("life") or 0) > 0:
                wear = float(wear_limit) / int(g["life"])
                src = f"game pace + life {int(g['life'])} laps · deg generic"
        out.append(CompoundSpec(code, alloc.label(code), alloc.color(code), off, deg, wear, 0.3, source=src))
    if not out:  # nothing known about the track: generic C3/C2/C1
        for code, role in ((18, "S"), (19, "M"), (20, "H")):
            off, deg, wear = _MANUAL[role]
            out.append(CompoundSpec(code, alloc.label(code) if alloc.roles else f"{role} (generic)", alloc.color(code), off, deg, wear, 0.3, source="manual · fill in"))
    return out


def ensure_overrides_schema(app_root: Path | None = None) -> None:
    with connect(app_root) as conn:
        conn.executescript(OVERRIDES_SCHEMA)


def load_overrides(track: str, state: str, app_root: Path | None = None) -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
    ensure_overrides_schema(app_root)
    with connect(app_root) as conn:
        row = conn.execute(
            "SELECT params_json, compounds_json FROM strategy_overrides WHERE track = ? AND state = ?",
            (normalize_track_name(track) or track, state),
        ).fetchone()
    if not row:
        return {}, {}
    params = json.loads(row["params_json"] or "{}")
    comps = {int(k): v for k, v in json.loads(row["compounds_json"] or "{}").items()}
    return params, comps


def save_overrides(
    track: str,
    state: str,
    params: RaceParams,
    specs: list[CompoundSpec],
    app_root: Path | None = None,
) -> None:
    ensure_overrides_schema(app_root)
    keep = ("laps", "pit_loss_s", "base_pace_s", "fuel_per_lap_kg", "fuel_effect_s_per_kg", "fuel_margin_laps",
            "wear_limit_pct", "sc_pit_factor", "require_two_compounds", "max_stops", "window_tolerance_s")
    comps = {
        str(s.code): {k: getattr(s, k) for k in ("offset_s", "deg_s_per_lap", "wear_pct_per_lap", "warmup_s", "use")}
        for s in specs
    }
    with connect(app_root) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO strategy_overrides (track, state, params_json, compounds_json, updated_at) VALUES (?, ?, ?, ?, ?)",
            (
                normalize_track_name(track) or track,
                state,
                json.dumps({k: getattr(params, k) for k in keep}),
                json.dumps(comps),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def clear_overrides(track: str, state: str, app_root: Path | None = None) -> None:
    ensure_overrides_schema(app_root)
    with connect(app_root) as conn:
        conn.execute(
            "DELETE FROM strategy_overrides WHERE track = ? AND state = ?", (normalize_track_name(track) or track, state)
        )


def apply_overrides(
    params: RaceParams,
    specs: list[CompoundSpec],
    saved_params: dict[str, Any],
    saved_specs: dict[int, dict[str, Any]],
) -> tuple[RaceParams, list[CompoundSpec]]:
    params = replace(params, **{k: v for k, v in saved_params.items() if hasattr(params, k)})
    out = []
    for s in specs:
        ov = saved_specs.get(s.code)
        out.append(replace(s, **{k: v for k, v in ov.items() if hasattr(s, k)}, source="manual") if ov else s)
    return params, out


# --------------------------------------------------------------------------- costs


@dataclass
class _Slot:
    """One tyre set: cumulative stint cost raw[L] / capped[L] (INF past the wear limit) for L laps on it."""

    wear: float
    raw: np.ndarray
    capped: np.ndarray
    max_laps: int


Inventory = dict[int, list[float]]  # {compound: [wear % of each available set]}
State = tuple[frozenset[int], tuple[int, ...]]  # (compounds run so far, sets consumed per compound)


class _Costs:
    """Cumulative stint costs per compound: cost[c][L] = time over base for a fresh L-lap stint.

    With ``inventory`` each compound has its own list of sets (freshest first), each with its own
    curve; ``slot(c, k)`` is the k-th freshest set. Without one every set is new and unlimited.
    """

    def __init__(self, specs: list[CompoundSpec], params: RaceParams, inventory: Inventory | None = None):
        self.params = params
        self.specs = {s.code: s for s in specs if s.use}
        self.raw: dict[int, np.ndarray] = {}
        self.capped: dict[int, np.ndarray] = {}
        self.max_laps: dict[int, int] = {}
        self._fresh: dict[int, _Slot] = {}
        for code, s in self.specs.items():
            slot = self._slot_for(s, 0.0)
            self._fresh[code] = slot
            self.raw[code], self.capped[code], self.max_laps[code] = slot.raw, slot.capped, slot.max_laps
        self.sets: dict[int, list[_Slot]] | None = None
        if inventory is not None:
            keep = params.max_stops + 1  # no plan fits more sets than stints
            self.sets = {}
            for code, s in self.specs.items():
                slots = [self._slot_for(s, w) for w in sorted(float(x) for x in inventory.get(code, []))[:keep]]
                self.sets[code] = [x for x in slots if x.max_laps >= 1]
        self.codes = list(self.specs)

    def _slot_for(self, s: CompoundSpec, wear: float) -> _Slot:
        R = self.params.laps
        cum = np.concatenate([[0.0], np.cumsum(s.lap_deltas(R, s.start_age(wear)))])
        m = s.max_laps(self.params.wear_limit_pct, R, wear)
        capped = cum.copy()
        capped[m + 1 :] = INF
        return _Slot(float(wear), cum, capped, m)

    def n_sets(self, code: int) -> int | None:
        """Usable sets of this compound, None = unlimited (no inventory)."""
        return None if self.sets is None else len(self.sets.get(code, []))

    def slot(self, code: int, k: int = 0) -> _Slot:
        return self._fresh[code] if self.sets is None else self.sets[code][k]

    def fits(self, compounds: tuple[int, ...]) -> bool:
        if self.sets is None:
            return True
        return all(compounds.count(c) <= (self.n_sets(c) or 0) for c in set(compounds))

    def slots_of(self, compounds: tuple[int, ...]) -> list[_Slot] | None:
        """The set each stint runs on: the k-th time a compound appears it gets its k-th freshest set."""
        compounds = tuple(compounds)
        if any(c not in self.specs for c in compounds) or not self.fits(compounds):
            return None
        seen: dict[int, int] = {}
        out = []
        for c in compounds:
            k = seen.get(c, 0)
            seen[c] = k + 1
            out.append(self.slot(c, k))
        return out

    def start_state(self, used: frozenset[int] = frozenset()) -> State:
        return frozenset(used), (tuple(0 for _ in self.codes) if self.sets is not None else ())

    def next_state(self, state: State, code: int) -> State | None:
        """State after fitting the next set of ``code``; None when no set of it is left."""
        mask, cnt = state
        if self.sets is not None:
            i = self.codes.index(code)
            if cnt[i] >= len(self.sets[code]):
                return None
            cnt = cnt[:i] + (cnt[i] + 1,) + cnt[i + 1 :]
        return mask | {code}, cnt

    def next_slot(self, state: State, code: int) -> _Slot:
        return self.slot(code, state[1][self.codes.index(code)] if self.sets is not None else 0)

    def dry_codes(self) -> set[int]:
        return {c for c in self.specs if is_slick(c)}

    def valid(self, used: frozenset[int]) -> bool:
        if not self.params.require_two_compounds or len(self.dry_codes()) < 2:
            return True
        return len(used & self.dry_codes()) >= 2

    def constant(self) -> float:
        p = self.params
        return p.base_pace_s * p.laps + float(np.sum(p.fuel_times()))


def _best_lengths(seq: tuple[int, ...], costs: _Costs) -> tuple[float, tuple[int, ...]] | None:
    R = costs.params.laps
    slots = costs.slots_of(seq)
    if slots is None:
        return None
    best = np.full(R + 1, INF)
    best[0] = 0.0
    backs = []
    for slot in slots:
        cost = slot.capped
        new = np.full(R + 1, INF)
        arg = np.zeros(R + 1, dtype=int)
        for m in range(1, R + 1):
            ls = np.arange(1, min(m, slot.max_laps) + 1)
            if not ls.size:
                continue
            vals = best[m - ls] + cost[ls]
            j = int(np.argmin(vals))
            new[m], arg[m] = vals[j], ls[j]
        backs.append(arg)
        best = new
    if not np.isfinite(best[R]):
        return None
    lens, m = [], R
    for arg in reversed(backs):
        lens.append(int(arg[m]))
        m -= int(arg[m])
    return float(best[R]), tuple(reversed(lens))


def _plan_cost(compounds: tuple[int, ...], stints: tuple[int, ...], costs: _Costs, *, capped: bool = True) -> float:
    slots = costs.slots_of(tuple(compounds))
    if slots is None:
        return INF
    total = sum((x.capped if capped else x.raw)[n] for x, n in zip(slots, stints))
    return costs.constant() + total + (len(stints) - 1) * costs.params.pit_loss_s


def _windows(plan: Plan, costs: _Costs) -> list[tuple[int, int]]:
    """Per stop: earliest..latest box lap within tolerance, other stops held where they are."""
    tol = costs.params.window_tolerance_s
    out = []
    for j in range(plan.stops):
        laps_ok = []
        for shift in range(-costs.params.laps, costs.params.laps + 1):
            st = list(plan.stints)
            st[j] += shift
            st[j + 1] -= shift
            if st[j] < 1 or st[j + 1] < 1:
                continue
            t = _plan_cost(plan.compounds, tuple(st), costs)
            if t <= plan.race_time + tol:
                laps_ok.append(int(np.cumsum(st)[j]))
        out.append((min(laps_ok), max(laps_ok)) if laps_ok else (plan.stop_laps[j], plan.stop_laps[j]))
    return out


def optimise(specs: list[CompoundSpec], params: RaceParams, inventory: Inventory | None = None) -> list[Plan]:
    """Every feasible compound multiset with up to max_stops stops, best stint lengths, fastest first.

    With ``inventory`` only the sets you have (see the module docstring).
    """
    costs = _Costs(specs, params, inventory)
    codes = [c for c in sorted(costs.specs, key=softness, reverse=True) if costs.n_sets(c) != 0]
    plans: list[Plan] = []
    seen: set[tuple[int, ...]] = set()
    for n_stints in range(1, params.max_stops + 2):
        for combo in itertools.combinations_with_replacement(codes, n_stints):
            key = tuple(sorted(combo))
            if key in seen or not costs.valid(frozenset(combo)) or not costs.fits(combo):
                continue
            seen.add(key)
            res = _best_lengths(combo, costs)
            if res is None:
                continue
            total, lens = res
            wears = tuple(x.wear for x in costs.slots_of(combo)) if costs.sets is not None else ()
            plan = Plan(compounds=combo, stints=lens, race_time=costs.constant() + total + (n_stints - 1) * params.pit_loss_s,
                        start_wear=wears)
            plan.windows = _windows(plan, costs)
            plans.append(plan)
    plans.sort(key=lambda p: p.race_time)
    return plans


def lap_times(plan: Plan, specs: list[CompoundSpec], params: RaceParams) -> np.ndarray:
    """Predicted lap times along a plan (pit loss booked on the in-lap of each stop)."""
    by_code = {s.code: s for s in specs}
    deltas = np.concatenate([by_code[c].lap_deltas(n, by_code[c].start_age(w))
                             for c, n, w in zip(plan.compounds, plan.stints, plan.wears())])
    t = params.base_pace_s + deltas + params.fuel_times()[: len(deltas)]
    for lap in plan.stop_laps:
        t[lap - 1] += params.pit_loss_s
    return t


def shortlist(plans: list[Plan], n: int = 8) -> list[Plan]:
    """Best plan per stop count always, then the fastest others, up to `n`; fastest first."""
    shown: list[Plan] = []
    for stops in sorted({p.stops for p in plans}):
        shown.append(next(p for p in plans if p.stops == stops))
    for p in plans:
        if len(shown) >= n:
            break
        if p not in shown:
            shown.append(p)
    shown.sort(key=lambda p: p.race_time)
    return shown


# --------------------------------------------------------------------------- sensitivity


SCENARIOS: tuple[tuple[str, dict[str, float]], ...] = (
    ("Degradation −25%", {"deg": 0.75}),
    ("Degradation +25%", {"deg": 1.25}),
    ("Wear +20%", {"wear": 1.2}),
    ("Pit loss −3 s", {"pit": -3.0}),
    ("Pit loss +3 s", {"pit": 3.0}),
)


def sensitivity(specs: list[CompoundSpec], params: RaceParams, baseline: Plan, inventory: Inventory | None = None) -> pd.DataFrame:
    """Best plan under each scenario, and what sticking to the baseline plan would cost there."""
    rows = []
    by_code = {s.code: s for s in specs}
    for name, mod in SCENARIOS:
        sp = [
            replace(
                s,
                deg_s_per_lap=s.deg_s_per_lap * mod.get("deg", 1.0),
                wear_pct_per_lap=s.wear_pct_per_lap * mod.get("wear", 1.0) if s.wear_pct_per_lap else None,
            )
            for s in specs
        ]
        pr = replace(params, pit_loss_s=max(0.0, params.pit_loss_s + mod.get("pit", 0.0)))
        plans = optimise(sp, pr, inventory)
        if not plans:
            continue
        best = plans[0]
        costs = _Costs(sp, pr, inventory)
        base_t = _plan_cost(baseline.compounds, baseline.stints, costs)
        same = sorted(best.compounds) == sorted(baseline.compounds) and best.stops == baseline.stops
        rows.append(
            {
                "Scenario": name,
                "Best plan": best.describe(by_code),
                "Same plan?": "yes" if same else "no",
                "Baseline plan costs": f"{base_t - best.race_time:+.1f} s" if np.isfinite(base_t) else "over wear limit",
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- in-race calls


def _cost_to_go(costs: _Costs, start: State | None = None) -> dict[State, np.ndarray]:
    """
    G[state][n]: best time over base for the last n laps when a new stint starts now (its pit
    loss already paid), given the state (compounds run so far, sets consumed). Only the states
    reachable from ``start`` (default: nothing run yet) are built.
    """
    start = start if start is not None else costs.start_state()
    states, queue = {start}, [start]
    while queue:
        st = queue.pop()
        for c in costs.codes:
            s2 = costs.next_state(st, c)
            if s2 is not None and s2 not in states:
                states.add(s2)
                queue.append(s2)
    R = costs.params.laps
    pit = costs.params.pit_loss_s
    G = {st: np.full(R + 1, INF) for st in states}
    for st in states:
        G[st][0] = 0.0 if costs.valid(st[0]) else INF
    moves = {}
    for st in states:
        moves[st] = []
        for c in costs.codes:
            s2 = costs.next_state(st, c)
            if s2 is not None:
                moves[st].append((costs.next_slot(st, c), s2))
    for n in range(1, R + 1):
        for st in states:
            best = INF
            for slot, s2 in moves[st]:
                ls = np.arange(1, min(n, slot.max_laps) + 1)
                if not ls.size:
                    continue
                rest = n - ls
                tail = np.where(rest > 0, pit + G[s2][rest], 0.0 if costs.valid(s2[0]) else INF)
                best = min(best, float(np.min(slot.capped[ls] + tail)))
            G[st][n] = best
    return G


@dataclass
class RaceCall:
    lap: int  # laps completed
    compound: int
    age: int
    box_now_s: float  # remaining time if boxing at the end of this lap (green)
    stay_out_s: float  # remaining time staying out at least one more lap
    box_under_sc_s: float
    undercut_gain_s: float | None  # first lap on new tyres vs one more lap on these


def race_calls(plan: Plan, specs: list[CompoundSpec], params: RaceParams, inventory: Inventory | None = None) -> pd.DataFrame:
    """Box / stay-out under green and under safety car on every lap along a plan."""
    costs = _Costs(specs, params, inventory)
    G = _cost_to_go(costs)
    R = params.laps
    rows = []
    lap = 0
    state = costs.start_state()
    best_new_first = {}  # best first-lap delta on the freshest set of each compound
    for c in costs.specs:
        if costs.n_sets(c) != 0:
            best_new_first[c] = float(costs.slot(c, 0).raw[1])
    for c, n in zip(plan.compounds, plan.stints):
        nxt = costs.next_state(state, c)
        if nxt is None:
            break
        slot = costs.next_slot(state, c)
        state = nxt
        used = state[0]
        for age in range(1, n + 1):
            lap += 1
            remaining = R - lap
            if remaining <= 0:
                break
            box = params.pit_loss_s + G[state][remaining]
            sc = params.pit_loss_s * params.sc_pit_factor + G[state][remaining]
            stay = INF
            raw = slot.raw
            for more in range(1, min(remaining, slot.max_laps - age) + 1):
                cost_more = raw[age + more] - raw[age]
                rest = remaining - more
                tail = params.pit_loss_s + G[state][rest] if rest > 0 else (0.0 if costs.valid(used) else INF)
                stay = min(stay, cost_more + tail)
            old_next = float(raw[age + 1] - raw[age]) if age + 1 < len(raw) else None
            fresh = min(best_new_first.values()) if best_new_first else None
            rows.append(
                {
                    "Lap": lap,
                    "On": _short(costs.specs, c),
                    "Age": age,
                    "Green: box now vs stay (s)": _diff(box, stay),
                    "SC: box now vs stay (s)": _diff(sc, stay),
                    "SC call": "BOX" if sc < stay else "stay out",
                    "Undercut gain (s)": round(old_next - fresh, 2) if old_next is not None and fresh is not None else None,
                }
            )
    return pd.DataFrame(rows)


def _diff(a: float, b: float) -> float | None:
    if not np.isfinite(a) and not np.isfinite(b):
        return None
    if not np.isfinite(a):
        return float("inf")
    if not np.isfinite(b):
        return float("-inf")
    return round(a - b, 2)


def plan_from_state(
    specs: list[CompoundSpec],
    params: RaceParams,
    *,
    lap: int,
    compound: int,
    age: int,
    used: frozenset[int] | set[int] | tuple[int, ...],
    inventory: Inventory | None = None,
) -> dict[str, Any] | None:
    """
    Live decision from the current race state (`lap` laps completed, `age` laps on `compound`,
    `used` = dry compounds run so far incl. this one; `inventory` = the sets still available,
    the fitted one left out — None treats every set as new and unlimited).

    Returns the cost (time over the cheapest continuation, seconds) of boxing now vs staying out,
    under green and under a safety car, the lap window in which boxing stays within
    `window_tolerance_s` of the best, and the compound to fit. None once the race is over or the
    current compound is not in the model.
    """
    costs = _Costs(specs, params, inventory)
    remaining = params.laps - int(lap)
    if remaining <= 0 or compound not in costs.specs:
        return None
    used_set = frozenset(c for c in used if c in costs.specs) | {compound}
    start = costs.start_state(used_set)
    G = _cost_to_go(costs, start)
    raw, pit = costs.raw[compound], params.pit_loss_s
    age = max(0, min(int(age), len(raw) - 1))
    max_more = max(0, min(remaining, costs.max_laps[compound] - age))
    stays_to_flag = costs.valid(used_set)

    def option(k: int, pit_s: float) -> float:
        """Run k more laps on these tyres, then box (k == remaining: run to the flag)."""
        run = float(raw[age + k] - raw[age])
        rest = remaining - k
        if rest <= 0:
            return run if stays_to_flag else INF
        return run + pit_s + G[start][rest]

    green = [option(k, pit) for k in range(0, max_more + 1)]
    box_now, sc_box = green[0], option(0, pit * params.sc_pit_factor)
    stay = min(green[1:], default=INF)
    best = min(green)
    k_best = int(np.argmin(green))
    no_more_stops = bool(np.isfinite(best)) and k_best == remaining  # running to the flag is the best option
    # the box window lists real stops only (k == remaining means "no stop")
    window = [k for k, v in enumerate(green) if k < remaining and v <= best + params.window_tolerance_s]
    # compound to fit when boxing at the best lap
    rest = remaining - k_best
    fit, fit_cost, fit_wear = None, INF, None
    if rest > 0:
        for c in costs.specs:
            s2 = costs.next_state(start, c)
            if s2 is None:
                continue
            slot = costs.next_slot(start, c)
            ls = np.arange(1, min(rest, slot.max_laps) + 1)
            tail = np.where(rest - ls > 0, pit + G[s2][np.maximum(rest - ls, 0)], np.where(costs.valid(s2[0]), 0.0, INF))
            v = float(np.min(slot.capped[ls] + tail)) if ls.size else INF
            if v < fit_cost:
                fit, fit_cost, fit_wear = c, v, (slot.wear if costs.sets is not None else None)
    return {
        "lap": int(lap),
        "laps_left": remaining,
        "box_now_s": box_now,
        "stay_out_s": stay,
        "box_under_sc_s": sc_box,
        "call_green": "BOX" if box_now <= stay else "STAY",
        "call_sc": "BOX" if sc_box < stay else "STAY",
        "best_in_laps": k_best,
        "box_window": [int(lap) + window[0], int(lap) + window[-1]] if (window and np.isfinite(best)) else None,
        "no_more_stops": no_more_stops,
        "fit_compound": fit,
        "fit_label": _short(costs.specs, fit) + _used(fit_wear) if fit is not None else None,
        "fit_wear": fit_wear,
        "sets_left": ({str(c): costs.n_sets(c) for c in costs.specs} if costs.sets is not None else None),
        "can_finish_without_stop": max_more == remaining and bool(np.isfinite(green[-1])),
    }


# --------------------------------------------------------------------------- post-race review


@dataclass
class RaceReview:
    actual: Plan
    actual_time: float | None  # None when the export is missing laps
    model_actual_time: float
    best: Plan
    strategy_cost_s: float  # model(actual plan) - model(best plan)
    execution_s: float | None  # actual - model(actual plan), over laps present and not behind the SC
    missing_laps: list[int] = field(default_factory=list)
    sc_laps: list[int] = field(default_factory=list)
    over_limit: list[tuple[int, int, int, int]] = field(default_factory=list)  # (stint #, compound, laps, max)


def game_pit_windows(df: pd.DataFrame) -> list[tuple[int, int]]:
    """The game's own (ideal, latest) pit lap suggestions, in the order they appeared."""
    if df is None or "pitIdealLap" not in df.columns or "pitLatestLap" not in df.columns:
        return []
    pairs = df[["pitIdealLap", "pitLatestLap"]].to_numpy(dtype=float)
    pairs = pairs[(pairs[:, 0] > 0) & (pairs[:, 1] > 0)]
    if not len(pairs):
        return []
    change = np.ones(len(pairs), dtype=bool)
    change[1:] = np.any(pairs[1:] != pairs[:-1], axis=1)
    out: list[tuple[int, int]] = []
    for ideal, latest in pairs[change].astype(int):
        if (int(ideal), int(latest)) not in out:
            out.append((int(ideal), int(latest)))
    return out


def race_lap_count(summary: pd.DataFrame) -> int:
    """Laps in the race by the game's lap numbers (laps the export skipped still count)."""
    return int(summary["lap"].max()) + 1 if not summary.empty else 0


def actual_plan(summary: pd.DataFrame) -> Plan | None:
    """The strategy that was run in a race session (compound + laps per tyre set, by lap number)."""
    stints = tyre_stints(summary)
    if not stints or any(s.compound is None for s in stints):
        return None
    firsts = [s.laps[0] for s in stints] + [race_lap_count(summary)]
    firsts[0] = 0
    lengths = tuple(int(b - a) for a, b in zip(firsts, firsts[1:]))
    return Plan(compounds=tuple(int(s.compound) for s in stints), stints=lengths, race_time=float(summary["lap_time"].sum()))


def review_unavailable_reason(summary: pd.DataFrame, specs_by_code: dict[int, CompoundSpec], params: RaceParams, state: str) -> str:
    """Why `review_race` returned None for this race."""
    plan = actual_plan(summary)
    if plan is None:
        return "No race review: a stint in this session has no compound logged."
    outside = sorted({c for c in plan.compounds if c not in specs_by_code})
    if outside:
        names = ", ".join(c_label(c) for c in outside)
        return f"No race review: this race used {names}, which the {state} model does not include — pick that track state."
    if sum(plan.stints) != params.laps:
        return f"No race review: race laps are set to {params.laps} but this race ran {sum(plan.stints)}."
    return "No race review for this session."


def review_race(summary: pd.DataFrame, specs: list[CompoundSpec], params: RaceParams) -> RaceReview | None:
    plan = actual_plan(summary)
    if plan is None or sum(plan.stints) != params.laps:
        return None
    by_code = {s.code: s for s in specs}
    if any(c not in by_code for c in plan.compounds):
        return None
    costs = _Costs(specs, params)
    model_actual = _plan_cost(plan.compounds, plan.stints, costs, capped=False)
    plans = optimise(specs, params)
    if not plans:
        return None
    best = plans[0]
    present = set(int(x) for x in summary["lap"])
    missing = [lap for lap in range(params.laps) if lap not in present]
    sc_laps = [int(x) for x in summary.loc[summary.get("lap_class", pd.Series(dtype=str)) == "sc", "lap"]]
    model_laps = lap_times(plan, specs, params)
    judged = summary[~summary["lap"].isin(sc_laps) & summary["lap"].between(0, params.laps - 1)]
    execution = (
        float(judged["lap_time"].sum() - model_laps[judged["lap"].astype(int).to_numpy()].sum()) if not judged.empty else None
    )
    over = [
        (k + 1, c, n, costs.max_laps[c])
        for k, (c, n) in enumerate(zip(plan.compounds, plan.stints))
        if n > costs.max_laps[c]
    ]
    return RaceReview(
        actual=plan,
        actual_time=None if missing else plan.race_time,
        model_actual_time=model_actual,
        best=best,
        strategy_cost_s=model_actual - best.race_time,
        execution_s=execution,
        missing_laps=missing,
        sc_laps=sc_laps,
        over_limit=over,
    )
