"""
Live setup duel: rank 2-3 complete setups on your own driving in practice. Pure and I/O-free.

The live engine only adapts packets into calls (``start``, ``on_lap``, ``on_garage``, ``on_tyre_sets``,
``on_tick``) and REST commands (``rank``, ``confirm``, ``skip_contestant``, ``stop``); every decision lives here. All
commands return ``view()``; invalid ones raise ``EngineerError(reason)`` (the same error class as the engineer).

Contestants are "A", "B", "C" in the order their setups are first seen (leaving the garage or finishing a lap).
A setup is recognised by the mechanical fingerprint (``setup_history.mech_fingerprint``: fuel, brake-bias mirror and
compound are ignored) computed WITHOUT the tyre pressures, so a pressure-only change is the same setup (and warns).
Brake bias and on-throttle diff are left out too: the driver moves them on the MFD while driving, so a change there
is still the same setup (said once in the feed); the contestant keeps the garage values seen when leaving the garage.
Laps count when valid, not in/out/pit, on the duel's compound (the first counted lap's) and not a mistake (> 2 s
slower than the contestant's median); target 4 per contestant, 3 needed, at most 5. Lap times are corrected for
fuel and tyre age (``lap_correction``). With every contestant at >= 3 counted laps and the car in the garage the
duel asks for your feel ranking; then it ranks with ``duel_ranking.rank_contestants`` (feel passed in) and waits
for you to confirm the winner.

Phases: idle -> running -> review (ranking shown, waiting for confirm) -> done.

``view()`` JSON shape (``null`` is the snapshot value while idle)::

    phase        "idle" | "running" | "review" | "done"
    track, session_type
    in_garage    bool
    n, target, min_laps, max_laps
    compound     int | null, compound_label  (the duel's compound, known after the first counted lap)
    contestants  [{key "A"|"B"|"C", label (given name or "Setup A"), name (given or null), assigned (setup seen),
                  on_car, counted, target, raw (laps seen), skipped, status "waiting|driving|done|skipped",
                  last_s, best_s, laps: [{lap, time_s}] (counted)}]
    current      key of the contestant on the car (by the last garage exit / lap) or null
    next         key of the contestant to drive now or null
    instruction  "Load setup B in the garage and drive 4 laps"
    detected     {key, warning}
    tyre_hint    "Fit a fresh set for Setup B ..." | "... correction accounts for tyre age" | null
    question     {pending (everyone >= 3 laps and in the garage), keys: [contestant keys to rank]}
    feel         null | {order: [keys, best first], note}
    ranking      null | rank_contestants output (contestants [{key, name, n_laps, rank, race_pace_s, quali_pace_s,
                 wear_pct_per_lap, race_cost_s, score_s, delta_s, balance}], order, winner, tie_break, decided,
                 noise_s, pairs, weights, cost_source, cost_note, callouts) + proposed
    winner       key you confirmed or null
    stop_reason  null | "stopped"
    feed         [{t, text}]  last ~20 lines (``drain_feed()`` yields only the new ones)

``result()`` is the JSON-able record to persist: mode "live", track, session_type, started_at, finished_at,
stop_reason, confirmed (bool), compound, correction, contestants (key, name, label, fingerprint, setup, counted laps
with corrected times), feel, ranking (null when fewer than two contestants had enough laps), winner (key or null),
winner_name, winner_setup, winner_fingerprint. Only a confirmed duel has a winner (and so becomes a baseline).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

import numpy as np

from telemetry import compounds
from telemetry.setup_history import mech_fingerprint

from .. import duel_ranking
from . import corner_ab
from .engineer import PRACTICE, EngineerError
from .lap_correction import Lap, correct_groups, representative_laps

TARGET_LAPS, MIN_LAPS, MAX_LAPS = 4, 3, 5
RAW_CAP = 8                        # laps looked at per contestant (mistakes do not count towards the max)
KEYS = ("A", "B", "C")
MAX_NAME = 40
WEAR_MIN_POINTS = 3
PRESSURE_KEYS = ("tyre_press_setup_0", "tyre_press_setup_1", "tyre_press_setup_2", "tyre_press_setup_3")
MFD_KEYS = ("brake_bias_setup", "diff_onThrottle_setup")   # adjustable on track, so not part of the setup's identity

PlanTime = Callable[[float], "float | None"]


def setup_fingerprints(setup: dict[str, float] | None) -> tuple[str | None, str | None]:
    """(fingerprint without tyre pressures, mechanical fingerprint with them) of a garage setup dict; MFD keys out."""
    if not setup:
        return None, None
    car = {k: v for k, v in setup.items() if k not in MFD_KEYS}
    return mech_fingerprint({k: v for k, v in car.items() if k not in PRESSURE_KEYS}), mech_fingerprint(car)


@dataclass
class _Contestant:
    key: str
    name: str | None
    fp: str | None = None                      # fingerprint without pressures
    full_fps: set[str] = field(default_factory=set)
    setup: dict[str, float] = field(default_factory=dict)   # last full setup seen with it (MFD keys: garage values)
    mfd_said: set[tuple] = field(default_factory=set)      # MFD values already reported in the feed
    laps: list[Lap] = field(default_factory=list)
    skipped: bool = False

    @property
    def label(self) -> str:
        return self.name or f"Setup {self.key}"


def _f(x: float | None, nd: int = 3) -> float | None:
    return None if x is None else round(float(x), nd)


class Duel:
    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self.phase = "idle"
        self.track = ""
        self.session_type = ""
        self.start_s = self.now_s = 0.0
        self.finished_s: float | None = None
        self.n = 0
        self.cs: list[_Contestant] = []
        self.in_garage = False
        self.sets: list[dict] = []
        self.fuel_k = 0.03
        self.deg_table: dict[int, float] = {}
        self.compound: int | None = None
        self.on_car: str | None = None
        self.warning: str | None = None
        self.feel: dict | None = None
        self.ranking: dict | None = None
        self.correction: dict | None = None
        self.winner: str | None = None
        self.stop_reason = ""
        self.feed: deque[dict] = deque(maxlen=20)
        self._new: list[dict] = []
        self._asked = False

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
        return self.phase in ("running", "review")

    def _live(self) -> list[_Contestant]:
        return [c for c in self.cs if not c.skipped]

    def _by_key(self, key: str | None) -> _Contestant | None:
        return next((c for c in self.cs if c.key == key), None)

    @staticmethod
    def _counted(c: _Contestant) -> list[Lap]:
        return representative_laps(c.laps)

    # -- start --------------------------------------------------------------------------------
    def start(self, n: int, names: list[str] | None, track: str, session_type: str, wet: bool, now_s: float,
              session_left_s: float | None = None, fuel_s_per_kg: float = 0.03,
              deg_s_per_lap: dict[int, float] | None = None) -> dict:
        if self.active:
            raise EngineerError("A setup duel is already running")
        if n not in (2, 3):
            raise EngineerError("A duel needs 2 or 3 setups")
        if session_type not in PRACTICE:
            raise EngineerError("The setup duel only runs in practice sessions")
        if wet:
            raise EngineerError("The setup duel does not run in wet conditions")
        given = [(x or "").strip()[:MAX_NAME] for x in (names or [])][:n]
        given += [""] * (n - len(given))
        sets = self.sets
        self._reset()
        self.sets = sets
        self.n, self.track, self.session_type = n, track, session_type
        self.start_s = self.now_s = float(now_s)
        self.fuel_k, self.deg_table = float(fuel_s_per_kg), dict(deg_s_per_lap or {})
        self.cs = [_Contestant(KEYS[i], given[i] or None) for i in range(n)]
        self.phase = "running"
        self._say(f"Setup duel on: {n} setups, {TARGET_LAPS} laps each. {self._instruction()}")
        hint = self._tyre_hint()
        if hint:
            self._say(hint)
        return self.view()

    # -- inputs -------------------------------------------------------------------------------
    def on_tyre_sets(self, sets: list[dict]) -> None:
        self.sets = list(sets)

    def on_tick(self, now_s: float, session_left_s: float | None = None) -> None:
        self.now_s = float(now_s)
        if self.phase == "running":
            self._refresh()

    def on_garage(self, in_garage: bool, now_s: float | None = None, setup: dict[str, float] | None = None) -> None:
        """Garage state each tick; ``setup`` (the car's current garage setup) is read when leaving the garage."""
        if now_s is not None:
            self.now_s = float(now_s)
        leaving = self.in_garage and not in_garage
        self.in_garage = bool(in_garage)
        if self.phase != "running":
            return
        if leaving and setup:
            self._identify(setup, "leaving the garage")
        self._refresh()

    def on_lap(self, lap: Lap) -> None:
        if self.phase != "running":
            return
        if not lap.flying:
            if not lap.valid:
                self._say(f"Lap {lap.lap} not counted: invalid")
            return
        if self.compound is not None and lap.compound is not None and lap.compound != self.compound:
            self.warning = f"Lap {lap.lap} not counted: fit the {compounds.c_label(self.compound)} used in this duel"
            self._say(self.warning)
            return
        c = self._identify(lap.setup, f"lap {lap.lap}")
        if c is None:
            self._say(f"Lap {lap.lap} not counted: {self.warning}")
            return
        if any(x.lap == lap.lap for x in c.laps):
            return
        if len(self._counted(c)) >= MAX_LAPS or len(c.laps) >= RAW_CAP:
            self.warning = f"{c.label} already has {MAX_LAPS} laps: lap {lap.lap} not counted"
            self._say(self.warning)
            return
        if self.compound is None and lap.compound is not None:
            self.compound = lap.compound
        c.laps.append(lap)
        n = len(self._counted(c))
        self._say(f"{c.label}: lap {min(n, TARGET_LAPS)} of {TARGET_LAPS}")
        if n == TARGET_LAPS:
            nxt = self._next()
            self._say(f"{c.label} done: back to the garage" + (f" and load {nxt.label}" if nxt else ""))
        self._refresh()

    def _identify(self, setup: dict[str, float] | None, where: str) -> _Contestant | None:
        """The contestant whose setup is on the car (assigning the next free slot to a new setup); None + warning."""
        fp, full = setup_fingerprints(setup)
        if fp is None or full is None:
            self.warning = "no garage setup received from the game"
            return None
        c = next((x for x in self.cs if x.fp == fp), None)
        if c is None:
            c = next((x for x in self._live() if x.fp is None), None)
            if c is None:
                have = ", ".join(x.label for x in self._live() if x.fp)
                self.warning = f"unknown setup ({where}): it matches none of {have}. Load one of them or stop the duel"
                return None
            c.fp = fp
            self.warning = None
            self._say(f"{c.label}: setup recognised")
        elif c.skipped:
            self.warning = f"{c.label} was skipped: load another setup"
            return None
        else:
            self.warning = None
            if c.full_fps and full not in c.full_fps:
                self.warning = f"Same setup as {c.label}, only the tyre pressures differ: counted as {c.label}"
        c.full_fps.add(full)
        self._take_setup(c, dict(setup or {}), garage=where == "leaving the garage")
        self.on_car = c.key
        if where == "leaving the garage" and len(self._counted(c)) >= TARGET_LAPS and self._next() not in (None, c):
            nxt = self._next()
            self.warning = f"{c.label} again: it already has {TARGET_LAPS} laps. Load {nxt.label} instead"
        if self.warning:
            self._say(self.warning)
        return c

    def _take_setup(self, c: _Contestant, setup: dict[str, float], garage: bool) -> None:
        """Store the setup on the car; on track the MFD keys keep their garage values (a change is said once)."""
        if not garage and c.setup:
            moved = tuple((k, setup[k]) for k in MFD_KEYS if k in setup and k in c.setup and setup[k] != c.setup[k])
            if moved and moved not in c.mfd_said:
                c.mfd_said.add(moved)
                self._say(f"Brake bias / differential changed on the MFD: still {c.label}")
            setup.update({k: c.setup[k] for k in MFD_KEYS if k in c.setup})
        c.setup = setup

    # -- progress -----------------------------------------------------------------------------
    def _next(self) -> _Contestant | None:
        """The contestant to drive now: the one on the car if unfinished, else the first unfinished."""
        cur = self._by_key(self.on_car)
        if cur is not None and not cur.skipped and len(self._counted(cur)) < TARGET_LAPS:
            return cur
        return next((c for c in self._live() if len(self._counted(c)) < TARGET_LAPS), None)

    def _ready(self) -> bool:
        live = self._live()
        return (self.phase == "running" and self.in_garage and len(live) >= 2
                and all(len(self._counted(c)) >= MIN_LAPS for c in live))

    def _refresh(self) -> None:
        if self._ready():
            if not self._asked:
                self._asked = True
                self._say("Back in the garage: rank the setups by feel, then see the numbers")
        else:
            self._asked = False

    def _tyre_hint(self) -> str | None:
        nxt = self._next()
        if self.phase != "running" or nxt is None or self._counted(nxt):
            return None
        rc = self.compound
        if rc is None:
            fitted = [s for s in self.sets if s.get("fitted") and s.get("compound") is not None]
            rc = int(fitted[0]["compound"]) if fitted else None
        if rc is None or not self.sets:
            return None
        fresh = [s for s in self.sets if s.get("compound") == rc and s.get("available") and not s.get("fitted")
                 and not s.get("wear")]
        need = sum(1 for c in self._live() if not self._counted(c))
        if len(fresh) >= need:
            return f"Spare fresh sets: fit a fresh set for {nxt.label} to keep the comparison clean."
        return "Not enough spare fresh sets: continue on the current set, the correction accounts for tyre age."

    # -- analysis -----------------------------------------------------------------------------
    @staticmethod
    def _wear_rate(laps: list[Lap]) -> float | None:
        """%/lap: slope of the mean tyre wear over lap number on the set with the most laps (>= 3 points)."""
        by_set: dict[Any, list[Lap]] = {}
        for x in laps:
            by_set.setdefault(x.tyre_set_idx, []).append(x)
        best = max(by_set.values(), key=len)
        pts = [(x.lap, x.wear_avg_pct if x.wear_avg_pct is not None else x.wear_max_pct) for x in best]
        pts = [(a, b) for a, b in pts if b is not None]
        if len(pts) < WEAR_MIN_POINTS or len({a for a, _ in pts}) < WEAR_MIN_POINTS:
            return None
        slope = float(np.polyfit([a for a, _ in pts], [b for _, b in pts], 1)[0])
        return slope if slope > 0 else None

    @staticmethod
    def _balance(laps: list[Lap], times: list[float]) -> dict[str, float | None] | None:
        """Raw understeer index per phase (median over corners) from the laps' corner profiles."""
        items = [(x.profile, times[i] / x.lap_time_s) for i, x in enumerate(laps) if x.profile and x.lap_time_s > 0]
        if len(items) < corner_ab.MIN_PROFILE_LAPS:
            return None
        avg = corner_ab.average_profile(items)
        out: dict[str, float | None] = {}
        for ph in corner_ab.PHASES:
            vals = [c["understeer"][ph] for c in avg.values() if c["understeer"][ph] is not None]
            out[ph] = float(np.median(vals)) if vals else None
        return out if any(v is not None for v in out.values()) else None

    def _rank(self, keys: list[str], feel_order: list[str] | None, plan_time: PlanTime | None,
              race_laps: int | None) -> dict:
        groups = {k: self._counted(self._by_key(k)) for k in keys}  # type: ignore[arg-type]
        cor = correct_groups(groups, self.fuel_k, self.deg_table)
        self.correction = {"deg_s_per_lap": cor.deg_s_per_lap, "deg_source": cor.deg_source,
                           "fuel_s_per_kg": self.fuel_k}
        cs = []
        for k in keys:
            c = self._by_key(k)
            assert c is not None
            cs.append(duel_ranking.Contestant(
                key=k, name=c.label, times=cor.times[k], wear_pct_per_lap=self._wear_rate(groups[k]),
                balance=self._balance(groups[k], cor.times[k]), extra={"fingerprint": c.fp}))
        return duel_ranking.rank_contestants(cs, plan_time=plan_time, race_laps=race_laps, feel_order=feel_order)

    # -- commands -----------------------------------------------------------------------------
    def rank(self, order: list[str], note: str | None = None, plan_time: PlanTime | None = None,
             race_laps: int | None = None) -> dict:
        """Your feel ranking (keys, best first) -> the app's ranking, to be confirmed."""
        if self.phase != "running" or not self._ready():
            raise EngineerError("Not ready: drive every setup (3 laps each) and come back to the garage first")
        keys = [c.key for c in self._live()]
        if sorted(order) != sorted(keys):
            raise EngineerError(f"Rank every setup exactly once: {', '.join(keys)}")
        self.feel = {"order": list(order), "note": (note or "").strip() or None}
        self.ranking = self._rank(keys, list(order), plan_time, race_laps)
        self.ranking["proposed"] = self.ranking["winner"]
        self.phase = "review"
        top = self._by_key(self.ranking["winner"])
        self._say(f"Ranking ready: {top.label if top else '?'} first. Confirm the winner.")
        return self.view()

    def confirm(self, winner: str) -> dict:
        if self.phase != "review":
            raise EngineerError("Nothing to confirm")
        c = self._by_key(winner)
        if c is None or c.skipped:
            raise EngineerError("Winner must be one of the contestants")
        self.winner = c.key
        self._say(f"{c.label} confirmed as the winner: it becomes the track baseline.")
        self._finish()
        return self.view()

    def skip_contestant(self) -> dict:
        """Drop the setup that is still to be driven (needs at least two left)."""
        if self.phase != "running":
            raise EngineerError("Nothing to skip")
        nxt = self._next()
        if nxt is None or len(self._live()) <= 2:
            raise EngineerError("Nothing to skip: a duel needs at least two setups")
        nxt.skipped = True
        if self.on_car == nxt.key:
            self.on_car = None
        self._say(f"{nxt.label} skipped.")
        self._refresh()
        return self.view()

    def stop(self, plan_time: PlanTime | None = None, race_laps: int | None = None) -> dict:
        if self.phase == "idle":
            raise EngineerError("No duel running")
        if self.phase != "done":
            self.stop_reason = "stopped"
            if self.phase == "running":
                ok = [c.key for c in self._live() if len(self._counted(c)) >= MIN_LAPS]
                if len(ok) >= 2:
                    self.ranking = self._rank(ok, None, plan_time, race_laps)
                    self.ranking["proposed"] = self.ranking["winner"]
            self._say("Duel stopped. What was measured is saved" + " (not confirmed, no baseline).")
            self._finish()
        return self.view()

    def _finish(self) -> None:
        self.phase = "done"
        self.finished_s = self.now_s

    # -- output -------------------------------------------------------------------------------
    def _instruction(self) -> str:
        if self.phase == "idle":
            return "Start a duel from the Live page."
        if self.phase == "done":
            return "Duel finished." if self.winner else "Duel stopped."
        if self.phase == "review":
            top = self._by_key((self.ranking or {}).get("winner"))
            return f"Confirm the winner (the numbers say {top.label if top else '?'})."
        if self._ready():
            return "Back in the garage: rank the setups by feel."
        nxt = self._next()
        if nxt is None:
            return "All setups driven: return to the garage."
        n = len(self._counted(nxt))
        if nxt.fp is None:
            return f"Load {nxt.label} in the garage and drive {TARGET_LAPS} laps"
        if self.on_car == nxt.key and not self.in_garage:
            return f"{nxt.label}: lap {min(n + 1, TARGET_LAPS)} of {TARGET_LAPS}"
        return f"Load {nxt.label} in the garage and drive laps ({n} of {TARGET_LAPS} done)"

    def _status(self, c: _Contestant) -> str:
        if c.skipped:
            return "skipped"
        n = len(self._counted(c))
        if n >= TARGET_LAPS:
            return "done"
        return "driving" if c.fp is not None and n > 0 else "waiting"

    def view(self) -> dict:
        nxt = self._next() if self.phase == "running" else None
        rows = []
        for c in self.cs:
            laps = self._counted(c)
            rows.append({
                "key": c.key, "label": c.label, "name": c.name, "assigned": c.fp is not None,
                "on_car": self.on_car == c.key and self.phase == "running", "counted": len(laps),
                "target": TARGET_LAPS, "raw": len(c.laps), "skipped": c.skipped, "status": self._status(c),
                "last_s": _f(laps[-1].lap_time_s) if laps else None,
                "best_s": _f(min(x.lap_time_s for x in laps)) if laps else None,
                "laps": [{"lap": x.lap, "time_s": _f(x.lap_time_s)} for x in laps],
            })
        return {
            "phase": self.phase, "track": self.track, "session_type": self.session_type, "in_garage": self.in_garage,
            "n": self.n, "target": TARGET_LAPS, "min_laps": MIN_LAPS, "max_laps": MAX_LAPS,
            "compound": self.compound,
            "compound_label": compounds.c_label(self.compound) if self.compound is not None else None,
            "contestants": rows, "current": self.on_car if self.phase == "running" else None,
            "next": nxt.key if nxt else None, "instruction": self._instruction(),
            "detected": {"key": self.on_car if self.phase == "running" else None, "warning": self.warning},
            "tyre_hint": self._tyre_hint(),
            "question": {"pending": self._ready(), "keys": [c.key for c in self._live()]},
            "feel": self.feel, "ranking": self.ranking, "winner": self.winner,
            "stop_reason": self.stop_reason or None, "feed": list(self.feed),
        }

    def result(self) -> dict:
        """JSON-able record of the duel (valid any time after ``start``)."""
        win = self._by_key(self.winner)
        rows = []
        for c in self.cs:
            laps = self._counted(c)
            rows.append({"key": c.key, "name": c.name, "label": c.label, "fingerprint": c.fp,
                         "setup": dict(c.setup), "skipped": c.skipped, "counted": len(laps),
                         "laps": [{"lap": x.lap, "time_s": _f(x.lap_time_s), "tyre_age": x.tyre_age_laps,
                                   "tyre_set": x.tyre_set_idx} for x in laps]})
        return {
            "mode": "live", "track": self.track, "session_type": self.session_type,
            "started_at": self.start_s, "finished_at": self.finished_s, "stop_reason": self.stop_reason or None,
            "confirmed": win is not None, "compound": self.compound, "correction": self.correction,
            "contestants": rows, "feel": self.feel, "ranking": self.ranking, "winner": self.winner,
            "winner_name": win.name if win else None, "winner_label": win.label if win else None,
            "winner_setup": dict(win.setup) if win else None, "winner_fingerprint": mech_fingerprint(win.setup) if win else None,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
