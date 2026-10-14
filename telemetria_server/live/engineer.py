"""
Live race engineer: an optometrist-style setup test for practice ("1 or 2?"). Pure and I/O-free.

The live engine only adapts packets into calls (``start``, ``on_lap``, ``on_garage``, ``on_tyre_sets``,
``on_tick``) and REST commands (``answer``, ``confirm``, ``skip``, ``next_phase``, ``revert``, ``stop``); every
decision lives here. All commands return ``view()``; invalid ones raise ``EngineerError(reason)``.

Phases: balance (~60% of the budget) -> quali (~15%) -> long_run (~25%) -> done. Balance tests one parameter
at a time (short program: 1, full: 3) as pairs of variants "1"/"2" (which one is the baseline is random and
hidden until you answered). Laps count when valid, not in/out/pit, matching the variant's garage value and not
> 2 s slower than the variant's median. Lap times are corrected for fuel and tyre age; verdict = corrected
mean difference vs a noise estimate (floor 0.10 s).

``view()`` JSON shape (``null`` is the snapshot value while the phase is idle)::

    phase        "idle" | "balance" | "quali" | "long_run" | "done"
    program      "short" | "full"
    track, session_type
    in_garage    bool
    budget       {total_s, left_s}
    param        {key, label, unit, index, of}  (balance: tested parameter; quali: key "quali")
    variants     {"1": 28, "2": 25}   garage display numbers (balance); strings for quali ("Front wing 28, ...")
    variant_text {"1": "Front wing 28", "2": "Front wing 25"}
    instruction  "Set Variant 2: Front wing 25"
    run          {variant: "1"|"2"|null (the variant to drive now), counted: {"1": n, "2": n},
                  target: 3, lap: laps of ``variant`` counted so far (max target)}
    detected     {variant: "1"|"2"|null (from the last lap's garage value), warning: str|null}
    tyre_hint    "Fit a fresh set for Variant 2 ..." | "... correction accounts for tyre age" | null
    question     {pending: bool (both variants >= 2 counted laps and car in garage), awaiting_confirm: bool,
                  proposed: "1"|"2"|null, tags: [allowed tag ids]}
    last_result  null | {pair, label, variants, delta_s (corrected, variant 2 - variant 1; <0 = 2 faster),
                  noise_s, confidence "none|medium|high", measurable, text, stopwatch_winner, n: {"1","2"},
                  sectors: [{sector, delta_s}] largest first, deg_s_per_lap, deg_source, your_answer
                  {verdict, strength, tags, note}, agreement "agree|disagree|null", agreement_text,
                  roles: {"1": "baseline"|"change"|"start"|"final", ...} (revealed after the answer),
                  proposed_winner}
    history      [{n, kind "param|quali|skipped", param, label, variants, roles, counted, delta_s, noise_s,
                  confidence, your_answer, winner, winner_role, outcome "changed|kept|same|skipped"}]
    settled      {key: {label, value (display), new (settled in this test)}}
    revert_proposal null | {param, label, from, to, race_s, quali_s, combined_s, text}  (answer with revert())
    long_run     null | {compound, label, laps: [{lap, time_s, corrected_s, wear_pct}], target,
                  wear_pct_per_lap, pace_deg_s_per_lap}
    feed         [{t, text}]  last ~20 lines (``drain_feed()`` yields only the new ones)

``result()`` is the JSON-able record to persist: view-like history plus track, program, started_at,
finished_at, baseline, final (garage dicts), quali, long_run and ``settled`` (new values this test).
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from telemetry import compounds
from telemetry.setup_tweaker import SETUP_PARAMS

PROGRAM_MIN = {"short": 18.0, "full": 50.0}
PROGRAM_PARAMS = {"short": 1, "full": 3}
BALANCE_FRAC, QUALI_FRAC, LONG_FRAC = 0.60, 0.15, 0.25
TARGET_LAPS, QUALI_LAPS, MIN_LAPS = 3, 2, 2
MISTAKE_S = 2.0
NOISE_FLOOR = 0.10
DEFAULT_DEG = 0.10
LONG_RUN_LAPS = 10
LONG_RUN_MIN = 8
RACE_WEIGHT, QUALI_WEIGHT = 0.7, 0.3
PRACTICE = ("FP1", "FP2", "FP3")
TAGS = ("entry_slow", "entry_fast", "mid_slow", "mid_fast", "exit_slow", "exit_fast",
        "braking_stability", "braking_lockups", "traction", "kerbs", "confidence")
VERDICTS, STRENGTHS = ("1", "2", "same"), ("slight", "clear")

# Test order and first gap (garage units). camber / toe are never tested.
PARAM_ORDER = ("wing_setup_0", "wing_setup_1", "diff_onThrottle_setup", "diff_offThrottle_setup", "arb_setup_0",
               "arb_setup_1", "susp_spring_setup_0", "susp_spring_setup_1", "susp_height_setup_0",
               "susp_height_setup_2", "brake_bias_setup", "brake_press_setup")
FIRST_GAP = {"wing_setup_0": 3, "wing_setup_1": 3, "diff_onThrottle_setup": 0.10, "diff_offThrottle_setup": 0.10,
             "arb_setup_0": 3, "arb_setup_1": 3, "susp_spring_setup_0": 5, "susp_spring_setup_1": 5,
             "susp_height_setup_0": 3, "susp_height_setup_2": 3, "brake_bias_setup": 0.02, "brake_press_setup": 0.05}
_LABELS = {"susp_height_setup_0": "Front ride height", "susp_height_setup_2": "Rear ride height",
           "brake_bias_setup": "Brake bias"}
_UNITS = {"brake_bias_setup": "%"}


class EngineerError(Exception):
    """A command or start that is not allowed right now; ``reason`` is shown to the driver."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class _Spec:
    key: str
    label: str
    unit: str
    scale: float
    lo: float
    hi: float
    step: float
    gap: float


def _build_specs() -> dict[str, _Spec]:
    by_key = {p.key: p for p in SETUP_PARAMS}
    return {k: _Spec(k, _LABELS.get(k, by_key[k].label), _UNITS.get(k, by_key[k].unit), by_key[k].display_scale,
                     by_key[k].min_v, by_key[k].max_v, by_key[k].step, FIRST_GAP[k]) for k in PARAM_ORDER}


SPECS = _build_specs()


@dataclass
class EngineerLap:
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
    setup: dict[str, float] = field(default_factory=dict)

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


@dataclass
class _Pair:
    kind: str                       # "param" | "quali" | "ref" (quali reference: nothing changed)
    keys: list[str]
    vals: dict[str, dict[str, float]]   # variant -> {setup key: value}
    roles: dict[str, str]           # variant -> baseline|change|start|final
    gap: float
    target: int
    key: str = ""
    laps: dict[str, list[EngineerLap]] = field(default_factory=lambda: {"1": [], "2": []})
    answer: dict | None = None
    proposed: str | None = None
    analysis: dict | None = None
    announced: bool = False
    direction: int = 1


def _f(x: float | None, nd: int = 3) -> float | None:
    return None if x is None else round(float(x), nd)


def _q(spec: _Spec, v: float) -> float:
    return round(round(v / spec.step) * spec.step, 4)


def _halve(spec: _Spec, gap: float) -> float:
    return max(spec.step, _q(spec, math.floor(gap / 2 / spec.step + 0.5) * spec.step))


def _alt(spec: _Spec, base: float, direction: int, gap: float) -> tuple[float, int]:
    """Value ``gap`` away from ``base`` in ``direction``; flips direction at a garage limit, else clamps."""
    for d in (direction, -direction):
        v = _q(spec, base + d * gap)
        if spec.lo - 1e-9 <= v <= spec.hi + 1e-9:
            return v, d
    return min(max(_q(spec, base + direction * gap), spec.lo), spec.hi), direction


def _disp(spec: _Spec, v: float) -> float:
    d = round(float(v) * spec.scale, 2)
    return int(d) if d == int(d) else d


def _text(spec: _Spec, v: float) -> str:
    return f"{spec.label} {_disp(spec, v)}{spec.unit}"


class Engineer:
    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)
        self._reset()

    def _reset(self) -> None:
        self.phase = "idle"
        self.program = "short"
        self.track = ""
        self.session_type = ""
        self.start_s = self.now_s = 0.0
        self.finished_s: float | None = None
        self.total_s = 0.0
        self.session_left_s: float | None = None
        self.in_garage = False
        self.sets: list[dict] = []
        self.fuel_k = 0.03
        self.deg_table: dict[int, float] = {}
        self.start_setup: dict[str, float] = {}
        self.work: dict[str, float] = {}      # tested keys -> current baseline value
        self.params: list[str] = []
        self.pidx = 0
        self.same_streak = 0
        self.pair: _Pair | None = None
        self.n_pairs = 0
        self.history: list[dict] = []
        self.accepted: list[dict] = []
        self.settled_prev: dict[str, float] = {}
        self.new_settled: dict[str, float] = {}
        self.feed: deque[dict] = deque(maxlen=20)
        self._new: list[dict] = []
        self.detected: str | None = None
        self.warning: str | None = None
        self.race_compound: int | None = None
        self.soft: int | None = None
        self.last_result: dict | None = None
        self.quali: dict | None = None
        self.revert_prop: dict | None = None
        self.reverted: list[dict] = []
        self.final_setup: dict[str, float] = {}
        self.lr_laps: list[dict] = []
        self.lr_ref_fuel: float | None = None
        self.stop_reason = ""

    # -- helpers ------------------------------------------------------------------------------
    def _say(self, text: str) -> None:
        line = {"t": self.now_s, "text": text}
        self.feed.append(line)
        self._new.append(line)

    def drain_feed(self) -> list[dict]:
        out, self._new = self._new, []
        return out

    @property
    def active(self) -> bool:
        return self.phase in ("balance", "quali", "long_run")

    def _left_s(self) -> float:
        left = self.total_s - (self.now_s - self.start_s)
        if self.session_left_s is not None:
            left = min(left, self.session_left_s)
        return max(0.0, left)

    def _spec(self) -> _Spec | None:
        return SPECS[self.pair.key] if self.pair and self.pair.kind == "param" else None

    # -- start --------------------------------------------------------------------------------
    def start(self, program: str, baseline: dict, track: str, session_type: str, wet: bool, now_s: float,
              minutes: float | None = None, session_left_s: float | None = None,
              settled: dict[str, float] | None = None, fuel_s_per_kg: float = 0.03,
              deg_s_per_lap: dict[int, float] | None = None) -> dict:
        if program not in PROGRAM_MIN:
            raise EngineerError("Program must be 'short' or 'full'")
        if self.active:
            raise EngineerError("An engineer program is already running")
        if session_type not in PRACTICE:
            raise EngineerError("The engineer only runs in practice sessions")
        if wet:
            raise EngineerError("The engineer does not run in wet conditions")
        if not baseline:
            raise EngineerError("No garage setup received from the game yet")
        sets, soft_hint = self.sets, self.soft
        self._reset()
        self.sets, self.soft = sets, soft_hint
        self.program, self.track, self.session_type = program, track, session_type
        self.start_s = self.now_s = float(now_s)
        self.session_left_s = session_left_s
        total = float(minutes if minutes else PROGRAM_MIN[program]) * 60.0
        self.total_s = min(total, session_left_s) if session_left_s else total
        self.fuel_k, self.deg_table = float(fuel_s_per_kg), dict(deg_s_per_lap or {})
        self.start_setup = {k: float(v) for k, v in baseline.items()}
        self.settled_prev = {k: float(v) for k, v in (settled or {}).items() if k in SPECS}
        self.work = {k: float(baseline[k]) for k in SPECS if k in baseline}
        for k, v in self.settled_prev.items():
            if k in self.work:
                if abs(v - self.work[k]) > SPECS[k].step / 2:
                    self._say(f"Settled earlier on this track: {_text(SPECS[k], v)} (set it before the first run)")
                self.work[k] = v
        self.start_setup.update(self.work)
        self.params = [k for k in PARAM_ORDER if k in self.work and k not in self.settled_prev][:PROGRAM_PARAMS[program]]
        self._update_soft()
        self.phase = "balance"
        self._say(f"Engineer on: {program} program, {self.total_s / 60:.0f} min. Balance test first.")
        self._next_param()
        self._refresh()
        return self.view()

    def _update_soft(self) -> None:
        cs = [int(s["compound"]) for s in self.sets if s.get("compound") is not None
              and compounds.is_slick(int(s["compound"]))]
        if cs:
            self.soft = max(cs, key=compounds.softness)

    # -- inputs -------------------------------------------------------------------------------
    def on_garage(self, in_garage: bool, now_s: float | None = None) -> None:
        if now_s is not None:
            self.now_s = float(now_s)
        self.in_garage = bool(in_garage)
        if self.active:
            self._refresh()

    def on_tyre_sets(self, sets: list[dict]) -> None:
        self.sets = list(sets)
        self._update_soft()

    def on_tick(self, now_s: float, session_left_s: float | None = None) -> None:
        self.now_s = float(now_s)
        if session_left_s is not None:
            self.session_left_s = session_left_s
        if self.active:
            self._refresh()

    def on_lap(self, lap: EngineerLap) -> None:
        if not self.active:
            return
        if self.phase == "long_run":
            self._lap_long(lap)
        elif self.pair is not None and self.pair.answer is None:
            self._lap_pair(lap)
        self._refresh()

    # -- laps in a pair -----------------------------------------------------------------------
    def _detect(self, pair: _Pair, setup: dict) -> str | None:
        for v in ("1", "2"):
            if v in pair.vals and all(k in setup and abs(float(setup[k]) - val) <= SPECS[k].step / 2 + 1e-9
                                      for k, val in pair.vals[v].items()):
                return v
        return None

    def _lap_pair(self, lap: EngineerLap) -> None:
        pair = self.pair
        assert pair is not None
        if not lap.flying:
            if not lap.valid:
                self._say(f"Lap {lap.lap} not counted: invalid")
            return
        if pair.kind != "param" and self.soft is not None and lap.compound is not None and lap.compound != self.soft:
            self.warning = f"Lap {lap.lap} not counted: fit the {compounds.c_label(self.soft)}"
            self._say(self.warning)
            return
        v = self._detect(pair, lap.setup)
        self.detected = v
        if v is None:
            self.warning = f"Lap {lap.lap} not counted: " + self._mismatch_text(pair, lap.setup)
            self._say(self.warning)
            return
        self.warning = None
        if any(x.lap == lap.lap for x in pair.laps[v]):
            return
        pair.laps[v].append(lap)
        if self.race_compound is None and pair.kind == "param" and lap.compound is not None:
            self.race_compound = lap.compound
        n = len(self._counted(pair, v))
        if pair.kind == "ref":
            self._say(f"Reference lap {min(n, pair.target)} of {pair.target}")
            return
        self._say(f"Variant {v}: lap {min(n, pair.target)} of {pair.target}")
        if n == pair.target:
            other = "2" if v == "1" else "1"
            if len(self._counted(pair, other)) >= pair.target:
                self._say("Both variants done: back to the garage")
            elif len(self._counted(pair, other)) < MIN_LAPS:
                self._say(f"Variant {v} done: back to the garage and set Variant {other}: {self._vtext(pair, other)}")

    def _mismatch_text(self, pair: _Pair, setup: dict) -> str:
        k = pair.keys[0]
        spec = SPECS[k]
        if k not in setup:
            return "no garage setup received"
        want = " or ".join(f"{self._vtext(pair, v)} (Variant {v})" for v in ("1", "2") if v in pair.vals)
        return f"{spec.label} is {_disp(spec, setup[k])}{spec.unit}, expected {want}"

    def _counted(self, pair: _Pair, v: str) -> list[EngineerLap]:
        laps = pair.laps.get(v, [])
        if not laps:
            return []
        med = float(np.median([x.lap_time_s for x in laps]))
        return [x for x in laps if x.lap_time_s <= med + MISTAKE_S]

    def _vtext(self, pair: _Pair, v: str) -> str:
        return ", ".join(_text(SPECS[k], val) for k, val in pair.vals[v].items())

    # -- pair lifecycle -----------------------------------------------------------------------
    def _next_param(self) -> None:
        while self.pidx < len(self.params):
            key = self.params[self.pidx]
            spec = SPECS[key]
            self.same_streak = 0
            alt, d = _alt(spec, self.work[key], 1, spec.gap)
            if abs(alt - self.work[key]) < spec.step / 2:
                self.pidx += 1
                continue
            self._new_pair(key, self.work[key], alt, spec.gap, d)
            return
        self._enter_quali()

    def _new_pair(self, key: str, base: float, alt: float, gap: float, direction: int) -> None:
        base_is_1 = self.rng.random() < 0.5
        vals = {"1": {key: base if base_is_1 else alt}, "2": {key: alt if base_is_1 else base}}
        roles = {"1": "baseline" if base_is_1 else "change", "2": "change" if base_is_1 else "baseline"}
        self.pair = _Pair("param", [key], vals, roles, gap, TARGET_LAPS, key=key, direction=direction)
        self.n_pairs += 1
        self.detected = self.warning = None
        spec = SPECS[key]
        self._say(f"Test {self.pidx + 1} of {len(self.params)}: {spec.label}. Set Variant 1: "
                  f"{self._vtext(self.pair, '1')}, then Variant 2: {self._vtext(self.pair, '2')}.")
        hint = self._tyre_hint()
        if hint:
            self._say(hint)

    def _tyre_hint(self) -> str | None:
        if self.phase != "balance":
            return None
        rc = self.race_compound
        if rc is None:
            fitted = [s for s in self.sets if s.get("fitted") and s.get("compound") is not None]
            rc = int(fitted[0]["compound"]) if fitted else None
        if rc is None or not self.sets:
            return None
        fresh = [s for s in self.sets if s.get("compound") == rc and s.get("available") and not s.get("fitted")
                 and not s.get("wear")]
        need = 1 + (1 if self.soft == rc else 0)  # long run + (quali if it uses the same compound)
        if len(fresh) > need:
            return "Spare fresh sets: fit a fresh set for Variant 2 to keep the comparison clean."
        return "No spare fresh sets: continue on the current set, the correction accounts for tyre age."

    def _need(self, pair: _Pair) -> str | None:
        c = {v: len(self._counted(pair, v)) for v in ("1", "2")}
        if pair.kind == "ref":
            return "1" if c["1"] < pair.target else None
        t = pair.target
        if c["1"] < t and c["2"] == 0:
            return "1"
        if c["2"] < t:
            return "2"
        return "1" if c["1"] < t else None

    def _ready(self) -> bool:
        p = self.pair
        if p is None or p.answer is not None:
            return False
        if p.kind == "ref":
            return self.in_garage and len(self._counted(p, "1")) >= p.target
        return self.in_garage and all(len(self._counted(p, v)) >= MIN_LAPS for v in ("1", "2")) \
            if p.kind == "param" else \
            self.in_garage and all(len(self._counted(p, v)) >= p.target for v in ("1", "2"))

    def _blocked(self) -> bool:
        p = self.pair
        return self.revert_prop is not None or (p is not None and p.kind == "param"
                                                and (p.answer is not None or self._ready()))

    # -- time and progress --------------------------------------------------------------------
    def _refresh(self) -> None:
        left = self._left_s()
        if self.phase == "balance" and left <= (QUALI_FRAC + LONG_FRAC) * self.total_s and not self._blocked():
            self._say("Ending balance, quali check next")
            self._enter_quali()
        elif self.phase == "quali" and left <= LONG_FRAC * self.total_s and not self._blocked():
            self._say("Time check: skipping the rest of the quali check, long run next")
            self._finish_quali(abandoned=True)
        if self.phase == "long_run" and left <= 0:
            self._say("Time is up: long run ends here")
            self._finish()
        if self.phase == "quali" and self._ready():
            self._finish_quali()
        p = self.pair
        if self.phase == "balance" and p is not None and p.kind == "param" and self._ready() and not p.announced:
            p.announced = True
            self._say("Back in the garage: which felt better, 1 or 2?")

    # -- analysis -----------------------------------------------------------------------------
    def _analyze(self, pair: _Pair) -> dict:
        laps = {v: self._counted(pair, v) for v in ("1", "2")}
        allp = laps["1"] + laps["2"]
        mids = [x.fuel_mid for x in allp if x.fuel_mid is not None]
        ref_fuel = float(np.mean(mids)) if mids else 0.0
        ref_age = float(np.mean([x.tyre_age_laps for x in allp]))

        def fuel_fix(x: EngineerLap) -> float:
            return self.fuel_k * (x.fuel_mid - ref_fuel) if x.fuel_mid is not None else 0.0

        deg, src = self._deg(allp, fuel_fix)
        corr: dict[str, list[float]] = {"1": [], "2": []}
        sect: dict[str, list[list[float]]] = {"1": [], "2": []}
        for v in ("1", "2"):
            for x in laps[v]:
                fix = fuel_fix(x) + deg * (x.tyre_age_laps - ref_age)
                corr[v].append(x.lap_time_s - fix)
                sect[v].append([(s - fix * s / x.lap_time_s) if s is not None else math.nan for s in x.sectors])
        m = {v: float(np.mean(corr[v])) for v in corr}
        delta = m["2"] - m["1"]
        var = sum((float(np.std(corr[v], ddof=1)) if len(corr[v]) > 1 else 0.0) ** 2 / len(corr[v]) for v in corr)
        noise = max(NOISE_FLOOR, math.sqrt(var))
        ratio = abs(delta) / noise
        measurable = ratio >= 1.0
        sectors = []
        for i in range(3):
            a = [r[i] for r in sect["1"] if not math.isnan(r[i])]
            b = [r[i] for r in sect["2"] if not math.isnan(r[i])]
            if a and b:
                sectors.append({"sector": i + 1, "delta_s": float(np.mean(b) - np.mean(a))})
        sectors.sort(key=lambda s: -abs(s["delta_s"]))
        winner = ("2" if delta < 0 else "1") if measurable else None
        text = (f"Variant {winner} is faster by {abs(delta):.3f} s/lap (corrected, noise {noise:.2f} s)"
                if winner else f"No measurable difference ({delta:+.3f} s/lap, noise {noise:.2f} s)")
        return {"delta_s": delta, "noise_s": noise, "confidence": "high" if ratio >= 2 else "medium" if measurable
                else "none", "measurable": measurable, "text": text, "stopwatch_winner": winner,
                "n": {v: len(corr[v]) for v in corr}, "means": m, "sectors": sectors, "deg_s_per_lap": deg,
                "deg_source": src, "fuel_s_per_kg": self.fuel_k}

    def _deg(self, laps: list[EngineerLap], fuel_fix) -> tuple[float, str]:
        by_set: dict[Any, list[EngineerLap]] = {}
        for x in laps:
            by_set.setdefault(x.tyre_set_idx, []).append(x)
        best = max(by_set.values(), key=len)
        if len(best) >= 4 and len({x.tyre_age_laps for x in best}) >= 3:
            slope = float(np.polyfit([x.tyre_age_laps for x in best], [x.lap_time_s - fuel_fix(x) for x in best], 1)[0])
            return min(max(slope, 0.0), 0.6), "fitted"
        comps = [x.compound for x in laps if x.compound is not None]
        if comps:
            c = max(set(comps), key=comps.count)
            if c in self.deg_table:
                return float(self.deg_table[c]), "compound"
        return DEFAULT_DEG, "default"

    def _compare(self, pair: _Pair, ans: dict) -> dict:
        a = pair.analysis
        assert a is not None
        v, noise, delta = ans["verdict"], a["noise_s"], a["delta_s"]
        sec = ", ".join(f"S{s['sector']} {s['delta_s']:+.2f} s" for s in a["sectors"]) or "no sector data"
        faster = a["stopwatch_winner"]
        if v == "same":
            ok, txt = (not a["measurable"], None)
            if not ok:
                txt = f"You felt no difference, but the stopwatch says Variant {faster} is {abs(delta):.2f} s/lap faster ({sec})."
        elif faster and faster != v:
            ok = False
            txt = (f"You prefer Variant {v}, but the stopwatch says Variant {faster} is {abs(delta):.2f} s/lap faster"
                   f" (corrected). Sector deltas, 2 minus 1: {sec}.")
        elif not a["measurable"] and ans["strength"] == "clear":
            ok = False
            txt = (f"You say Variant {v} clearly, but the stopwatch cannot separate them ({delta:+.2f} s/lap, "
                   f"noise {noise:.2f} s). Sector deltas, 2 minus 1: {sec}.")
        else:
            ok = True
            txt = None
        if ok:
            txt = ("Stopwatch agrees: " if a["measurable"] else "Stopwatch finds nothing either: ") + a["text"] + "."
        return {"agreement": "agree" if ok else "disagree", "agreement_text": txt}

    # -- commands -----------------------------------------------------------------------------
    def answer(self, verdict: str, strength: str = "slight", tags: list[str] | None = None,
               note: str | None = None) -> dict:
        p = self.pair
        if self.phase != "balance" or p is None or p.kind != "param":
            raise EngineerError("No question to answer right now")
        if p.answer is not None:
            raise EngineerError("This question is already answered")
        if not self._ready():
            raise EngineerError("Not ready: drive both variants and come back to the garage first")
        tags = list(tags or [])
        if verdict not in VERDICTS:
            raise EngineerError("Verdict must be '1', '2' or 'same'")
        if strength not in STRENGTHS:
            raise EngineerError("Strength must be 'slight' or 'clear'")
        if len(tags) > 3 or len(set(tags)) != len(tags) or any(t not in TAGS for t in tags):
            raise EngineerError("Use up to three distinct tags from the list")
        p.answer = {"verdict": verdict, "strength": strength, "tags": tags, "note": (note or "").strip() or None}
        p.analysis = self._analyze(p)
        cmp = self._compare(p, p.answer)
        self.last_result = {**self._result_row(p), **cmp, "your_answer": p.answer}
        self._say(cmp["agreement_text"] or p.analysis["text"])
        if verdict == "same":
            self.same_streak += 1
            self._finish_pair(None)
        else:
            p.proposed = verdict
            self.last_result["proposed_winner"] = verdict
            self._say(f"Confirm Variant {verdict} as the winner (or pick the other).")
        return self.view()

    def confirm(self, winner: str) -> dict:
        p = self.pair
        if p is None or p.answer is None or p.proposed is None or self.phase != "balance":
            raise EngineerError("Nothing to confirm")
        if winner not in ("1", "2"):
            raise EngineerError("Winner must be '1' or '2'")
        self.same_streak = 0
        self._finish_pair(winner)
        return self.view()

    def _finish_pair(self, winner: str | None) -> None:
        p = self.pair
        assert p is not None and p.analysis is not None
        spec = SPECS[p.key]
        base_v = next(v for v in ("1", "2") if p.roles[v] == "baseline")
        change_v = "2" if base_v == "1" else "1"
        old = self.work[p.key]
        a = p.analysis
        change_delta = a["means"][change_v] - a["means"][base_v]
        if winner is None:
            outcome, win_role = "same", "baseline"
        else:
            win_role = p.roles[winner]
            outcome = "changed" if win_role == "change" else "kept"
        if win_role == "change":
            self.work[p.key] = p.vals[change_v][p.key]
            self.accepted.append({"param": p.key, "old": old, "new": self.work[p.key], "delta_s": change_delta})
            self._say(f"{spec.label} now {_disp(spec, self.work[p.key])}{spec.unit} (corrected {change_delta:+.3f} s/lap).")
        else:
            self._say(f"Keeping {_text(spec, old)}.")
        row = {**self._result_row(p), "n": self.n_pairs, "kind": "param", "param": p.key, "label": spec.label,
               "your_answer": p.answer, "winner": winner, "winner_role": win_role, "outcome": outcome,
               "change_delta_s": change_delta, "agreement": (self.last_result or {}).get("agreement"),
               "agreement_text": (self.last_result or {}).get("agreement_text"),
               "gap": _disp(spec, p.gap)}
        self.history.append(row)
        # stop rule: two "same" in a row or the smallest step reached
        done = ""
        if self.same_streak >= 2:
            done = "two answers of no difference"
        elif p.gap <= spec.step + 1e-9:
            done = "smallest step reached"
        if done:
            self.new_settled[p.key] = self.work[p.key]
            self._say(f"{spec.label} settled at {_disp(spec, self.work[p.key])}{spec.unit} ({done}).")
            self.pidx += 1
            self._next_param()
        else:
            gap = _halve(spec, p.gap)
            alt, d = _alt(spec, self.work[p.key], p.direction, gap)
            if abs(alt - self.work[p.key]) < spec.step / 2:
                self.new_settled[p.key] = self.work[p.key]
                self.pidx += 1
                self._next_param()
            else:
                self._new_pair(p.key, self.work[p.key], alt, gap, d)
        self._refresh()

    def skip(self) -> dict:
        if self.phase != "balance" or self.pair is None or self.revert_prop is not None:
            raise EngineerError("Nothing to skip: skipping only works while testing a parameter")
        p = self.pair
        self.history.append({"n": self.n_pairs, "kind": "skipped", "param": p.key, "label": SPECS[p.key].label,
                             "outcome": "skipped", "variants": self._pair_disp(p), "winner": None})
        self._say(f"Skipping {SPECS[p.key].label}.")
        self.pidx += 1
        self._next_param()
        self._refresh()
        return self.view()

    def next_phase(self) -> dict:
        if not self.active:
            raise EngineerError("No program running")
        if self.revert_prop is not None:
            self.revert(False)
            return self.view()
        if self.phase == "balance":
            self._say("Ending balance early, quali check next")
            self._enter_quali()
        elif self.phase == "quali":
            self._finish_quali(abandoned=True)
        else:
            self._finish()
        self._refresh()
        return self.view()

    def stop(self) -> dict:
        if not self.active and self.phase != "done":
            raise EngineerError("No program running")
        if self.phase != "done":
            self.stop_reason = "stopped"
            self._say("Engineer stopped. What was decided so far is saved.")
            self._finish()
        return self.view()

    def revert(self, accept: bool) -> dict:
        if self.revert_prop is None:
            raise EngineerError("No revert proposal pending")
        r, self.revert_prop = self.revert_prop, None
        if accept:
            self.final_setup[r["key"]] = r["old"]
            if r["key"] in self.new_settled:
                self.new_settled[r["key"]] = r["old"]
            self.reverted.append(r)
            self._say(f"Revert {r['label']} to {r['from_to'][1]} in the garage before the long run.")
        else:
            self._say(f"Keeping {r['label']} as tested.")
        self._enter_long_run()
        return self.view()

    # -- quali check and parc ferme -----------------------------------------------------------
    def _enter_quali(self) -> None:
        self.phase = "quali"
        self.revert_prop = None
        changed = [k for k in self.work if abs(self.work[k] - self.start_setup.get(k, self.work[k])) > SPECS[k].step / 2]
        self.final_setup = dict(self.start_setup)
        self.final_setup.update(self.work)
        self.detected = self.warning = None
        soft = f"the {compounds.c_label(self.soft)}" if self.soft is not None else "the softest tyre"
        if not changed:
            self.pair = _Pair("ref", [], {"1": {}}, {"1": "start"}, 0.0, QUALI_LAPS)
            self._say(f"Quali check: nothing changed, 2 flying laps on {soft} at low fuel for reference.")
            return
        final_is_1 = self.rng.random() < 0.5
        fin = {k: self.work[k] for k in changed}
        start = {k: self.start_setup[k] for k in changed}
        self.pair = _Pair("quali", changed, {"1": fin if final_is_1 else start, "2": start if final_is_1 else fin},
                          {"1": "final" if final_is_1 else "start", "2": "start" if final_is_1 else "final"},
                          0.0, QUALI_LAPS)
        self._say(f"Quali check on {soft}, low fuel, {QUALI_LAPS} flying laps each. "
                  f"Variant 1: {self._vtext(self.pair, '1')}. Variant 2: {self._vtext(self.pair, '2')}.")

    def _finish_quali(self, abandoned: bool = False) -> None:
        p = self.pair
        qd = None
        if p is not None and p.kind == "quali" and all(len(self._counted(p, v)) >= MIN_LAPS for v in ("1", "2")):
            p.analysis = self._analyze(p)
            fin_v = next(v for v in ("1", "2") if p.roles[v] == "final")
            a = p.analysis
            qd = a["means"][fin_v] - a["means"]["2" if fin_v == "1" else "1"]
            self.quali = {"delta_s": qd, "noise_s": a["noise_s"], "variants": {v: self._vtext(p, v) for v in p.vals},
                          "roles": p.roles, "n": a["n"], "sectors": a["sectors"], "text": a["text"]}
            self.history.append({**self._result_row(p), "n": self.n_pairs + 1, "kind": "quali", "param": "quali",
                                 "label": "Quali check", "winner": None, "outcome": "kept"})
            self._say(f"Quali check: final setup is {qd:+.3f} s/lap vs the starting setup (soft, corrected).")
        elif p is not None and p.kind == "ref" and len(self._counted(p, "1")) >= p.target:
            self.quali = {"delta_s": 0.0, "reference_only": True}
        self.pair = None
        self._parc_ferme(qd)

    def _parc_ferme(self, quali_delta: float | None) -> None:
        race = float(sum(a["delta_s"] for a in self.accepted))
        combined = RACE_WEIGHT * race + QUALI_WEIGHT * (quali_delta or 0.0)
        if self.quali is not None:
            self.quali.update(race_s=race, combined_s=combined)
        if combined > 0 and self.accepted:
            last = self.accepted[-1]
            spec = SPECS[last["param"]]
            self.revert_prop = {
                "key": last["param"], "param": last["param"], "label": spec.label, "old": last["old"],
                "from": _disp(spec, last["new"]), "to": _disp(spec, last["old"]),
                "from_to": (_disp(spec, last["new"]), _disp(spec, last["old"])),
                "race_s": race, "quali_s": quali_delta, "combined_s": combined,
                "text": (f"Parc ferme: 70% race ({race:+.3f}) + 30% quali ({quali_delta or 0.0:+.3f}) = "
                         f"{combined:+.3f} s/lap, worse than the starting setup. Revert {spec.label} "
                         f"to {_disp(spec, last['old'])}{spec.unit}?")}
            self._say(self.revert_prop["text"])
            return
        self._enter_long_run()

    # -- long run -----------------------------------------------------------------------------
    def _enter_long_run(self) -> None:
        self.phase = "long_run"
        self.pair = None
        self.revert_prop = None
        self.lr_laps, self.lr_ref_fuel = [], None
        self._say(self._lr_instruction() + ". Final setup in; come back when done.")

    def _lr_instruction(self) -> str:
        c = self.race_compound
        return f"Long run: {LONG_RUN_MIN}–{LONG_RUN_LAPS} laps on " + (compounds.c_label(c) if c is not None
                                                                         else "the race compound")

    def _lap_long(self, lap: EngineerLap) -> None:
        if not lap.flying:
            return
        if self.race_compound is not None and lap.compound is not None and lap.compound != self.race_compound:
            self.warning = f"Lap {lap.lap} not counted: fit the {compounds.c_label(self.race_compound)}"
            self._say(self.warning)
            return
        if self.race_compound is None:
            self.race_compound = lap.compound
        if any(x["lap"] == lap.lap for x in self.lr_laps):
            return
        if self.lr_ref_fuel is None and lap.fuel_mid is not None:
            self.lr_ref_fuel = lap.fuel_mid
        fix = self.fuel_k * (lap.fuel_mid - self.lr_ref_fuel) if lap.fuel_mid is not None and self.lr_ref_fuel is not None else 0.0
        self.lr_laps.append({"lap": lap.lap, "time_s": lap.lap_time_s, "corrected_s": lap.lap_time_s - fix,
                             "wear_pct": lap.wear_max_pct, "age": lap.tyre_age_laps})
        self._say(f"Long run: lap {len(self.lr_laps)} of {LONG_RUN_LAPS}, {lap.lap_time_s:.3f} s "
                  f"(fuel-corrected {lap.lap_time_s - fix:.3f}).")
        if len(self.lr_laps) >= LONG_RUN_LAPS:
            self._finish()

    def _long_run_summary(self) -> dict | None:
        if self.phase not in ("long_run", "done") or (self.phase == "done" and not self.lr_laps):
            return None
        laps = self._lr_valid()
        wear = [x["wear_pct"] for x in laps if x["wear_pct"] is not None]
        age = [x["age"] for x in laps]
        wpl = float((wear[-1] - wear[0]) / max(1, len(wear) - 1)) if len(wear) >= 2 else None
        dpl = float(np.polyfit(age, [x["corrected_s"] for x in laps], 1)[0]) if len(laps) >= 3 and len(set(age)) >= 3 else None
        c = self.race_compound
        return {"compound": c, "label": compounds.c_label(c) if c is not None else None, "laps": laps,
                "target": LONG_RUN_LAPS, "wear_pct_per_lap": _f(wpl), "pace_deg_s_per_lap": _f(dpl)}

    def _lr_valid(self) -> list[dict]:
        if not self.lr_laps:
            return []
        med = float(np.median([x["time_s"] for x in self.lr_laps]))
        return [{**x, "time_s": _f(x["time_s"]), "corrected_s": _f(x["corrected_s"])}
                for x in self.lr_laps if x["time_s"] <= med + MISTAKE_S]

    def _finish(self) -> None:
        if self.phase == "long_run":
            s = self._long_run_summary()
            if s and s["laps"]:
                parts = [f"{len(s['laps'])} laps"]
                if s["wear_pct_per_lap"] is not None:
                    parts.append(f"wear {s['wear_pct_per_lap']:.2f} %/lap")
                if s["pace_deg_s_per_lap"] is not None:
                    parts.append(f"pace {s['pace_deg_s_per_lap']:+.3f} s/lap")
                self._say("Long run done: " + ", ".join(parts) + ".")
        self.phase = "done"
        self.pair = None
        self.revert_prop = None
        self.finished_s = self.now_s
        self._say("Program finished.")

    # -- output -------------------------------------------------------------------------------
    def _pair_disp(self, p: _Pair) -> dict:
        if p.kind == "param":
            spec = SPECS[p.key]
            return {v: _disp(spec, p.vals[v][p.key]) for v in ("1", "2")}
        return {v: self._vtext(p, v) for v in p.vals} if p.kind == "quali" else {}

    def _result_row(self, p: _Pair) -> dict:
        a = p.analysis or {}
        out = {"pair": self.n_pairs, "label": SPECS[p.key].label if p.kind == "param" else "Quali check",
               "variants": self._pair_disp(p), "roles": dict(p.roles) if p.analysis else None,
               "counted": a.get("n"), "delta_s": _f(a.get("delta_s")), "noise_s": _f(a.get("noise_s")),
               "confidence": a.get("confidence"), "measurable": a.get("measurable"), "text": a.get("text"),
               "stopwatch_winner": a.get("stopwatch_winner"), "n": a.get("n"),
               "sectors": [{"sector": s["sector"], "delta_s": _f(s["delta_s"])} for s in a.get("sectors", [])],
               "deg_s_per_lap": _f(a.get("deg_s_per_lap")), "deg_source": a.get("deg_source"),
               "laps": {v: [x.lap for x in self._counted(p, v)] for v in ("1", "2")}}
        return out

    def _instruction(self) -> str:
        p = self.pair
        if self.phase == "idle":
            return "Start a program from the Live page."
        if self.phase == "done":
            return "Program finished."
        if self.phase == "long_run":
            return self._lr_instruction()
        if self.revert_prop is not None:
            return "Decide: revert the last change or keep it."
        if p is None:
            return ""
        if p.answer is not None:
            return f"Confirm the winner (your pick: Variant {p.proposed})." if p.proposed else ""
        if self._ready():
            return "Back in the garage: answer 1, 2 or no difference." if p.kind == "param" else \
                "Quali check done."
        if p.kind == "ref":
            return f"Quali check: {p.target} flying laps on the softest tyre at low fuel."
        n = self._need(p)
        if n is None:
            return "Both variants done: return to the garage."
        pre = "Quali check: " if p.kind == "quali" else ""
        return f"{pre}Set Variant {n}: {self._vtext(p, n)}"

    def view(self) -> dict:
        p = self.pair
        counted = {v: len(self._counted(p, v)) for v in ("1", "2")} if p else {"1": 0, "2": 0}
        need = self._need(p) if p else None
        spec = self._spec()
        run = {"variant": need, "counted": counted, "target": p.target if p else TARGET_LAPS,
               "lap": min(counted.get(need, 0), p.target) if (p and need) else 0}
        if p is None:
            param = None
        elif p.kind == "param":
            param = {"key": p.key, "label": SPECS[p.key].label, "unit": SPECS[p.key].unit,
                     "index": self.pidx + 1, "of": len(self.params)}
        else:
            param = {"key": "quali", "label": "Quali check", "unit": "", "index": 1, "of": 1}
        question_pending = bool(self.phase == "balance" and p is not None and p.kind == "param"
                                and p.answer is None and self._ready())
        settled = {k: {"label": SPECS[k].label, "value": _disp(SPECS[k], v), "new": k in self.new_settled}
                   for k, v in {**self.settled_prev, **self.new_settled}.items()}
        return {
            "phase": self.phase, "program": self.program, "track": self.track, "session_type": self.session_type,
            "in_garage": self.in_garage,
            "budget": {"total_s": _f(self.total_s, 1), "left_s": _f(self._left_s(), 1)},
            "param": param,
            "variants": self._pair_disp(p) if p and p.kind != "ref" else None,
            "variant_text": {v: self._vtext(p, v) for v in p.vals} if p and p.kind != "ref" else None,
            "instruction": self._instruction(), "run": run,
            "detected": {"variant": self.detected, "warning": self.warning},
            "tyre_hint": self._tyre_hint() if p is not None and p.kind == "param" else None,
            "question": {"pending": question_pending, "awaiting_confirm": bool(p and p.answer and p.proposed),
                         "proposed": p.proposed if p else None, "tags": list(TAGS)},
            "last_result": self.last_result,
            "history": list(self.history), "settled": settled,
            "revert_proposal": {k: v for k, v in self.revert_prop.items() if k not in ("old", "from_to")}
            if self.revert_prop else None,
            "long_run": self._long_run_summary(), "feed": list(self.feed),
        }

    def result(self) -> dict:
        """JSON-able record of what was decided (valid any time after ``start``)."""
        return {
            "track": self.track, "session_type": self.session_type, "program": self.program,
            "started_at": self.start_s, "finished_at": self.finished_s, "stop_reason": self.stop_reason or None,
            "baseline": dict(self.start_setup), "final": dict(self.final_setup or {**self.start_setup, **self.work}),
            "pairs": list(self.history), "accepted": [dict(a) for a in self.accepted],
            "reverted": [{"param": r["param"], "from": r["from"], "to": r["to"]} for r in self.reverted],
            "quali": self.quali, "long_run": self._long_run_summary(),
            "settled": dict(self.new_settled), "race_compound": self.race_compound,
        }
