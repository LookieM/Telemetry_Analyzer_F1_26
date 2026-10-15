"""LiveEngine: turns the latest packets into the 10 Hz snapshot, events and the live strategy call."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from telemetry import compounds, engineer_log, tyres
from telemetry.corners import normalize_track_name
from telemetry.garage import garage_from_raw
from telemetry.metrics import FUEL_S_PER_KG

from ..udp import srt_columns as cols
from ..udp import structs
from .duel import Duel
from .engineer import PRACTICE, Engineer, EngineerError, EngineerLap
from .lap_profile import LapProfiler
from .state import (PID_DAMAGE, PID_EVENT, PID_LAP, PID_PARTICIPANTS, PID_SESSION, PID_SETUP, PID_STATUS,
                    PID_TELEMETRY, PID_TELEMETRY2, LiveState)

log = logging.getLogger("telemetria.live")

WHEELS = ("RL", "RR", "FL", "FR")  # UDP array order
WEATHER = ("Clear", "Light cloud", "Overcast", "Light rain", "Heavy rain", "Storm")
SC_NAMES = ("", "SC", "VSC", "formation")
FUEL_LAPS_WINDOW = 3

# (UDP field, label, group). Aero parts cost lap time; only the front wing can be changed in a stop.
DAMAGE_PARTS = (
    ("m_frontLeftWingDamage", "Front wing L", "aero"), ("m_frontRightWingDamage", "Front wing R", "aero"),
    ("m_rearWingDamage", "Rear wing", "aero"), ("m_floorDamage", "Floor", "aero"),
    ("m_diffuserDamage", "Diffuser", "aero"), ("m_sidepodDamage", "Sidepod", "aero"),
    ("m_gearBoxDamage", "Gearbox", "power"), ("m_engineDamage", "Engine", "power"),
)
WEAR_PARTS = (
    ("m_engineICEWear", "ICE"), ("m_engineMGUKWear", "MGU-K"), ("m_engineMGUHWear", "MGU-H"),
    ("m_engineESWear", "ES"), ("m_engineCEWear", "CE"), ("m_engineTCWear", "TC"),
)
DAMAGE_HIT_PCT = 5      # a jump this big between two ticks is a new hit
WING_ADVICE_PCT = 10    # below this a front-wing change is never worth a stop
WING_BROKEN_PCT = 50    # at this level the car is undriveable at pace: box without waiting for a measurement
SC_PIT_FACTOR = 0.55    # share of the pit loss paid under SC/VSC (same default as the strategy model)


def _ms(part, minutes) -> float:
    return (int(minutes) * 60000 + int(part)) / 1000.0


def _text(raw) -> str:
    return bytes(raw).split(b"\x00", 1)[0].decode("utf-8", "replace")


@dataclass
class RefLap:
    dist: np.ndarray
    time: np.ndarray
    total: float
    label: str
    lap: int

    def at(self, d: float) -> float:
        return float(np.interp(d, self.dist, self.time))


@dataclass
class LapRecord:
    lap: int
    time: float
    valid: bool
    pit: bool
    sc: bool
    fuel_start: float | None
    fuel_end: float | None
    damage: dict[str, int] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        """A lap whose time says something about pace: no pit lane, no SC/VSC, timer ran normally."""
        return not self.pit and not self.sc and self.time > 20.0

    @property
    def fuel_mid(self) -> float | None:
        if self.fuel_start is None or self.fuel_end is None:
            return None
        return (self.fuel_start + self.fuel_end) / 2.0


def damage_loss(history: list[LapRecord], hit_lap: int, *, fuel_s_per_kg: float = FUEL_S_PER_KG) -> dict | None:
    """Measured lap-time cost of a hit on ``hit_lap``: clean laps after vs up to 3 clean laps before,
    corrected for the fuel burned in between (lighter car = faster, so the raw gap understates the loss).
    Tyre wear between the two groups is not removed, so the figure leans slightly high."""
    before = [h for h in history if h.lap < hit_lap and h.clean][-3:]
    after = [h for h in history if h.lap > hit_lap and h.clean]
    if not before or not after:
        return None
    t_b = float(np.median([h.time for h in before]))
    t_a = float(np.median([h.time for h in after]))
    f_b = [h.fuel_mid for h in before if h.fuel_mid is not None]
    f_a = [h.fuel_mid for h in after if h.fuel_mid is not None]
    fuel_fix = fuel_s_per_kg * (float(np.mean(f_b)) - float(np.mean(f_a))) if f_b and f_a else 0.0
    return {"loss_s": t_a - t_b + fuel_fix, "laps_before": len(before), "laps_after": len(after),
            "fuel_fix_s": fuel_fix}


def wing_advice(wing_pct: int, loss: dict | None, *, laps_left: int, pit_loss_s: float, wing_change_s: float,
                planned_stop_lap: int | None, lap_now: int, sc: bool = False) -> dict:
    """Should we stop for a new front wing? Transparent arithmetic, no hidden model."""
    if wing_pct < WING_ADVICE_PCT or laps_left <= 1:
        return {"call": None, "text": None}
    if wing_pct >= WING_BROKEN_PCT:
        return {"call": "BOX", "text": f"Front wing {wing_pct}%: box for a new wing now"
                + (" — the stop is cheaper under the safety car." if sc else ".")}
    if sc:
        cost = pit_loss_s * SC_PIT_FACTOR + wing_change_s
        return {"call": "BOX", "text": f"Front wing {wing_pct}%: safety car out — a wing stop costs only "
                f"~{cost:.0f} s now (vs {pit_loss_s + wing_change_s:.0f} s under green)."}
    if loss is None:
        return {"call": "MEASURE", "text": f"Front wing {wing_pct}%: need one clean lap after the hit to measure the cost."}
    per_lap = max(0.0, loss["loss_s"])
    if planned_stop_lap is not None and lap_now <= planned_stop_lap <= lap_now + laps_left:
        until = max(0, planned_stop_lap - lap_now)
        return {"call": "AT_STOP", "text": (
            f"Front wing {wing_pct}%: ~{per_lap:.2f} s/lap. Change it at the planned stop "
            f"(lap {planned_stop_lap}, ~{per_lap * until:.1f} s until then); +{wing_change_s:.0f} s on that stop.")}
    stay_cost = per_lap * laps_left
    stop_cost = pit_loss_s + wing_change_s
    call = "BOX" if stay_cost > stop_cost else "STAY"
    return {"call": call, "text": (
        f"Front wing {wing_pct}%: ~{per_lap:.2f} s/lap × {laps_left} laps = {stay_cost:.1f} s "
        f"vs stop {pit_loss_s:.0f} s + wing {wing_change_s:.0f} s = {stop_cost:.1f} s → {call}.")}


class LiveEngine:
    def __init__(self, state: LiveState, app_root: Path | None = None, *, wing_change_s: float = 5.0) -> None:
        self.s = state
        self.root = app_root
        self.wing_change_s = wing_change_s
        self.sess_ref: RefLap | None = None
        self.last_ref: RefLap | None = None
        self.history: list[LapRecord] = []
        self._cur_d: list[float] = []
        self._cur_t: list[float] = []
        self._cur_pit = False
        self._cur_sc = False
        self._lap_num: int | None = None
        self._fuel_at_lap: dict[int, float] = {}
        self._fuel_per_lap: list[float] = []
        self._pit_prev = 0
        self._sc_prev = 0
        self._baselined = False
        self._events: deque[dict] = deque(maxlen=100)
        self._used: set[int] = set()
        self._track_name: str | None = None
        self.strategy: dict | None = None
        self.strategy_dirty = False
        self._call_prev: str | None = None
        self._target_cache: dict[tuple, Any] = {}
        self._wear_limit: float | None = None
        self._track_len = 0.0
        self._dmg_prev: dict[str, int] | None = None
        self._hits: dict[str, int] = {}   # part label -> lap of the last hit
        self._comp_prev: int | None = None
        self.game_tyres_pending: dict | None = None  # picked up by the server loop and stored off-thread
        self._game_tyres_done: tuple | None = None
        # engineer adapter state: API threads call the commands while the server loop ticks, hence the lock
        self.engineer = Engineer()
        self._eng_lock = threading.Lock()
        self.engineer_save_pending: dict | None = None  # picked up by the server loop and stored off-thread
        self._eng_saved = False
        # the setup duel is the other live program (one at a time); it shares the engineer's lock
        self.duel = Duel()
        self.duel_save_pending: dict | None = None
        self._duel_saved = False
        # set by the ingest: () -> the running SessionRecorder; without it laps carry no corner profile
        self.recorder_source: Callable[[], Any] | None = None
        self._profiler = LapProfiler(app_root)
        self._reset_lap_marks()
        self._set_first_age: dict[int, int] = {}

    # -- helpers ------------------------------------------------------------------------------
    def _emit(self, kind: str, text: str, **extra) -> None:
        self._events.append({"type": "event", "kind": kind, "text": text, "t": time.time(), **extra})

    def pop_events(self) -> list[dict]:
        out = list(self._events)
        self._events.clear()
        return out

    def _targets(self, compound: int | None, kind: str):
        key = (compound, kind)
        if key not in self._target_cache:
            self._target_cache[key] = tyres.get_targets(compound, self.root, kind=kind)
        return self._target_cache[key]

    def _reset_for_new_session(self) -> None:
        self.sess_ref = self.last_ref = None
        self.history = []
        self._cur_d, self._cur_t = [], []
        self._cur_pit = self._cur_sc = False
        self._lap_num = None
        self._fuel_at_lap.clear()
        self._fuel_per_lap.clear()
        self._used.clear()
        self.strategy = None
        self._call_prev = None
        self._pit_prev = self._sc_prev = 0
        self._baselined = False
        self._dmg_prev = None
        self._hits = {}
        self._comp_prev = None
        self._game_tyres_done = None
        self.game_tyres_pending = None
        self._end_engineer()
        self._reset_lap_marks()
        self._set_first_age = {}
        self.s.new_session = False

    def _damage_now(self) -> dict[str, int] | None:
        dmg = self.s.get(PID_DAMAGE)
        if dmg is None:
            return None
        c = dmg["m_carDamageData"][self.s.player]
        return {label: int(c[f]) for f, label, _g in DAMAGE_PARTS}

    # -- per-tick bookkeeping (called by the server loop at the snapshot rate) -----------------
    def tick(self) -> None:
        s = self.s
        if s.new_session:
            self._reset_for_new_session()
        lapd = s.get(PID_LAP)
        sess = s.get(PID_SESSION)
        if lapd is None or sess is None:
            return
        p = s.player
        me = lapd["m_lapData"][p]
        track = cols.track_name(int(sess["m_trackId"]))
        if track != self._track_name:
            self._track_name = track
            self.strategy_dirty = True  # warm the compound model before the first lap ends

        lap_num = int(me["m_currentLapNum"])
        dist = float(me["m_lapDistance"])
        cur_t = int(me["m_currentLapTimeInMS"]) / 1000.0
        status = s.get(PID_STATUS)
        if status is not None:
            fuel = float(status["m_carStatusData"][p]["m_fuelInTank"])
            self._fuel_at_lap.setdefault(lap_num, fuel)
            comp = int(status["m_carStatusData"][p]["m_actualTyreCompound"])
            if compounds.is_slick(comp):
                self._used.add(comp)
            if comp != self._comp_prev:  # new set fitted: the plan and its compound model change
                self._comp_prev = comp
                self.strategy_dirty = True
        if self._lap_num is None:
            self._lap_num = lap_num
        if lap_num != self._lap_num:
            self._on_new_lap(lap_num, me)
        if dist >= 0 and (not self._cur_d or dist > self._cur_d[-1] - 1e-6):
            self._cur_d.append(dist)
            self._cur_t.append(cur_t)
        self._mark_lap(me, status)

        pit = int(me["m_pitStatus"])
        self._track_len = float(sess["m_trackLength"])
        sc = int(sess["m_safetyCarStatus"])
        self._cur_pit = self._cur_pit or pit > 0
        self._cur_sc = self._cur_sc or sc in (1, 2)
        if not self._baselined:  # first reading of a session: remember, do not announce
            self._baselined = True
            self._pit_prev, self._sc_prev = pit, sc
            self._dmg_prev = self._damage_now()
        if pit != self._pit_prev:
            if pit and not self._pit_prev:
                self._emit("pit_in", "In the pit lane")
            elif not pit:
                self._emit("pit_out", "Left the pit lane")
            self._pit_prev = pit
        if sc != self._sc_prev:
            self._emit("sc", f"{SC_NAMES[min(sc, 3)] or 'Green'} " + ("deployed" if sc else "ended"), sc=sc)
            self._sc_prev = sc
            self.strategy_dirty = True
        self._check_damage(lap_num)
        self._read_events()
        self._collect_game_tyres(sess)
        self._engineer_tick(me, sess)

    def _collect_game_tyres(self, sess) -> None:
        """Once per session and track: hand the game's tyre allocation / pace deltas / life to the server."""
        ts = self.s.player_tyre_sets
        key = (self.s.uid, int(sess["m_trackId"]))
        if ts is None or key == self._game_tyres_done:
            return
        sets = [{"actual": int(x["m_actualTyreCompound"]), "visual": int(x["m_visualTyreCompound"]),
                 "life": int(x["m_useableLife"]), "delta_ms": int(x["m_lapDeltaTime"])} for x in ts["m_tyresetData"]]
        self._game_tyres_done = key
        self.game_tyres_pending = {
            "track": cols.track_name(int(sess["m_trackId"])), "sets": sets,
            "total_laps": int(sess["m_totalLaps"]) or None,
            "session_type": cols.session_type_name(int(sess["m_sessionType"])),
        }

    def _check_damage(self, lap_num: int) -> None:
        now = self._damage_now()
        if now is None:
            return
        prev = self._dmg_prev or {k: 0 for k in now}
        hits = [(k, now[k] - prev.get(k, 0), now[k]) for k in now if now[k] - prev.get(k, 0) >= DAMAGE_HIT_PCT]
        repaired = [k for k in now if prev.get(k, 0) - now[k] >= DAMAGE_HIT_PCT]
        for k in repaired:
            self._hits.pop(k, None)
        if hits:
            for k, _d, _v in hits:
                self._hits[k] = lap_num
            self._emit("damage", ", ".join(f"{k} {v}%" for k, _d, v in hits))
            self.strategy_dirty = True
        self._dmg_prev = now

    def _read_events(self) -> None:
        ev = self.s.get(PID_EVENT)
        if ev is None:
            return
        code = _text(ev["m_eventStringCode"])
        key = (code, int(self.s.header["m_frameIdentifier"]))
        if key == getattr(self, "_last_ev_key", None):
            return
        self._last_ev_key = key
        if code == "PENA":
            d = np.frombuffer(ev["m_eventDetails"].tobytes()[: structs.EventDetails_Penalty_DT.itemsize],
                              dtype=structs.EventDetails_Penalty_DT)[0]
            if int(d["vehicleIdx"]) == self.s.player:
                t = int(d["time"])
                self._emit("penalty", f"Penalty +{t} s" if t < 100 else "Penalty")
        elif code == "FLBK":
            self._emit("flashback", "Flashback")
        elif code == "SEND":
            self._emit("session_end", "Session ended")

    def _on_new_lap(self, lap_num: int, me) -> None:
        prev = self._lap_num
        self._lap_num = lap_num
        fuel_start, fuel_end = self._fuel_at_lap.get(prev), self._fuel_at_lap.get(lap_num)
        if fuel_start is not None and fuel_end is not None and lap_num == prev + 1:
            used = fuel_start - fuel_end
            if used > 0.05:
                self._fuel_per_lap.append(used)
        last_ms = int(me["m_lastLapTimeInMS"])
        d, t = np.array(self._cur_d), np.array(self._cur_t)
        full_lap = bool(last_ms > 20000 and len(d) > 100 and self._track_len
                        and d.min() < 0.05 * self._track_len and d.max() > 0.95 * self._track_len
                        and (t > 0.5).mean() > 0.95)  # the lap timer actually ran all lap
        valid = self._lap_valid(prev)
        if lap_num == prev + 1 and last_ms > 0:
            self.history.append(LapRecord(prev, last_ms / 1000.0, valid, self._cur_pit, self._cur_sc,
                                          fuel_start, fuel_end, dict(self._dmg_prev or {})))
            self._engineer_lap(prev, last_ms / 1000.0, valid and not self._cur_invalid, fuel_start, fuel_end)
        if full_lap:
            t2 = t.copy()
            t2[-1] = max(t2[-1], last_ms / 1000.0)
            ref = RefLap(d.copy(), t2, last_ms / 1000.0, "last lap", prev)
            self.last_ref = ref
            if valid and not self._cur_pit and (self.sess_ref is None or ref.total < self.sess_ref.total):
                self.sess_ref = RefLap(ref.dist, ref.time, ref.total, "session best", prev)
        self._cur_d, self._cur_t = [], []
        self._cur_pit = self._cur_sc = False
        self._reset_lap_marks()
        self.strategy_dirty = True

    # -- engineer adapter (no decisions here: packets in, engineer calls out) ------------------
    def _reset_lap_marks(self) -> None:
        self._cur_dstat: set[int] = set()
        self._cur_s1 = self._cur_s2 = 0.0
        self._cur_invalid = False
        self._age0: int | None = None

    def _mark_lap(self, me, status) -> None:
        """Per-lap facts the engineer needs that are gone by the time the lap flips."""
        self._cur_dstat.add(int(me["m_driverStatus"]))
        self._cur_invalid = self._cur_invalid or bool(int(me["m_currentLapInvalid"]))
        s1 = _ms(me["m_sector1TimeInMSPart"], me["m_sector1TimeMinutesPart"])
        s2 = _ms(me["m_sector2TimeInMSPart"], me["m_sector2TimeMinutesPart"])
        self._cur_s1, self._cur_s2 = s1 or self._cur_s1, s2 or self._cur_s2
        if status is not None:
            age = int(status["m_carStatusData"][self.s.player]["m_tyresAgeLaps"])
            if self._age0 is None:
                self._age0 = age
            idx = self._fitted_idx()
            if idx is not None:
                self._set_first_age.setdefault(idx, age)

    def _fitted_idx(self) -> int | None:
        ts = self.s.player_tyre_sets
        return int(ts["m_fittedIdx"]) if ts is not None else None

    def _tyre_sets(self) -> list[dict]:
        ts = self.s.player_tyre_sets
        if ts is None:
            return []
        return [{"compound": int(x["m_actualTyreCompound"]), "available": bool(x["m_available"]),
                 "fitted": i == int(ts["m_fittedIdx"]), "wear": int(x["m_wear"]), "life": int(x["m_useableLife"])}
                for i, x in enumerate(ts["m_tyresetData"]) if int(x["m_actualTyreCompound"]) > 0]

    def _player_setup(self) -> dict[str, float]:
        pk = self.s.get(PID_SETUP)
        if pk is None:
            return {}
        return garage_from_raw(cols.setup_row(pk["m_carSetups"][self.s.player]))

    def _eng_pump(self) -> None:
        """Feed lines become live events; a finished program is handed over for storing (caller holds the lock)."""
        for line in self.engineer.drain_feed():
            self._emit("engineer", line["text"])
        for line in self.duel.drain_feed():
            self._emit("engineer", line["text"])
        if self.duel.phase == "done" and not self._duel_saved:
            self._duel_saved = True
            self.duel_save_pending = self.duel.result()
        if self.engineer.phase == "done" and not self._eng_saved:
            self._eng_saved = True
            self.engineer_save_pending = self.engineer.result()

    def _lap_profile(self, lap: int) -> dict | None:
        """Corner profile of the lap that just ended, from the recorder's frame of it (recorder laps are 0-based).
        The recorder is fed before the engine ticks, so the lap's bins are complete here. Never raises."""
        if self.recorder_source is None:
            return None
        try:
            rec = self.recorder_source()
            if rec is None:
                return None
            from telemetry.loader import normalize_frame

            frame = rec.lap_frame(lap - 1)
            if frame.empty:
                return None
            return self._profiler.profile(self._track_name, normalize_frame(frame), self._track_len or rec.track_length)
        except Exception:
            log.exception("engineer: corner profile of lap %s failed", lap)
            return None

    def _engineer_lap(self, lap: int, time_s: float, valid: bool, fuel_start, fuel_end) -> None:
        if not self.engineer.active and not self.duel.active:
            return
        status, dmg = self.s.get(PID_STATUS), self.s.get(PID_DAMAGE)
        st = status["m_carStatusData"][self.s.player] if status is not None else None
        sectors = [self._cur_s1 or None, self._cur_s2 or None]
        s3 = time_s - sum(sectors) if all(sectors) else None
        idx, age0 = self._fitted_idx(), self._age0 or 0
        el = EngineerLap(
            lap=lap, lap_time_s=time_s, valid=valid, in_lap=2 in self._cur_dstat, out_lap=3 in self._cur_dstat,
            pit=self._cur_pit, s1=sectors[0], s2=sectors[1], s3=s3 if s3 and s3 > 0 else None,
            fuel_start=fuel_start, fuel_end=fuel_end,
            compound=int(st["m_actualTyreCompound"]) if st is not None else None, tyre_set_idx=idx,
            fresh_set=bool(idx is not None and self._set_first_age.get(idx, age0) == 0),
            tyre_age_laps=age0,
            wear_max_pct=float(max(dmg["m_carDamageData"][self.s.player]["m_tyresWear"])) if dmg is not None else None,
            wear_avg_pct=float(np.mean(dmg["m_carDamageData"][self.s.player]["m_tyresWear"])) if dmg is not None else None,
            setup=self._player_setup(), profile=self._lap_profile(lap))
        with self._eng_lock:
            if self.engineer.active:
                self.engineer.on_lap(el)
            if self.duel.active:
                self.duel.on_lap(el)
            self._eng_pump()

    def _engineer_tick(self, me, sess) -> None:
        if not self.engineer.active and not self.duel.active:
            return
        with self._eng_lock:
            practice = cols.session_type_name(int(sess["m_sessionType"])) in PRACTICE
            in_garage = int(me["m_driverStatus"]) == 0
            if self.engineer.active:
                if not practice:
                    self.engineer.stop()
                else:
                    self.engineer.on_tyre_sets(self._tyre_sets())
                    self.engineer.on_garage(in_garage, self.s.last_t)
                    self.engineer.on_tick(self.s.last_t, int(sess["m_sessionTimeLeft"]) or None)
            if self.duel.active:
                if not practice:
                    self.duel.stop()
                else:
                    self.duel.on_tyre_sets(self._tyre_sets())
                    # the setup is read on the tick the car leaves the garage
                    self.duel.on_garage(in_garage, self.s.last_t, self._player_setup() if (self.duel.in_garage and not in_garage) else None)
                    self.duel.on_tick(self.s.last_t, int(sess["m_sessionTimeLeft"]) or None)
            self._eng_pump()

    def _end_engineer(self) -> None:
        """New session: stop a running program (what was decided is stored) and start with a fresh engineer."""
        with self._eng_lock:
            if self.engineer.active:
                self.engineer.stop()
            if self.duel.active:
                self.duel.stop()
            self._eng_pump()
            self.engineer = Engineer()
            self._eng_saved = False
            self.duel = Duel()
            self._duel_saved = False

    def engineer_models(self, track: str) -> tuple[float, dict[int, float]]:
        """Library fuel effect and per-compound degradation for the track (heavy: call outside the lock)."""
        fuel_k, deg = FUEL_S_PER_KG, {}
        if self.root is None:
            return fuel_k, deg
        try:
            fuel_k = float(tyres.library_race_stats(self.root).fuel_s_per_kg)
            model = tyres.track_compound_model(normalize_track_name(track) or track, "dry", self.root)
            deg = {int(c): float(m.deg_s_per_lap) for c, m in model.compounds.items()}
        except Exception:
            log.exception("engineer: no fuel / degradation model for %s", track)
        return fuel_k, deg

    def _generator_confidence(self, track: str) -> dict[str, str] | None:
        """Per-parameter confidence of the track's ACTIVE baseline when it came from the generator, else None."""
        if self.root is None:
            return None
        try:
            from telemetry import duel_store
            active = duel_store.get_baselines(normalize_track_name(track) or track, self.root)["active"]
            if not active or active.get("source") != "generator":
                return None
            conf = (active.get("meta") or {}).get("confidence")
            return {str(k): str(v) for k, v in conf.items()} if isinstance(conf, dict) and conf else None
        except Exception:
            log.exception("engineer: could not read the generated baseline confidence for %s", track)
            return None

    def engineer_start(self, program: str, minutes: float | None = None) -> dict:
        s = self.s
        sess, lapd, stat = s.get(PID_SESSION), s.get(PID_LAP), s.get(PID_STATUS)
        if sess is None or lapd is None:
            raise EngineerError("No live session data yet")
        track = cols.track_name(int(sess["m_trackId"]))
        comp = int(stat["m_carStatusData"][s.player]["m_actualTyreCompound"]) if stat is not None else None
        wet = int(sess["m_weather"]) >= 3 or (comp is not None and comp in compounds.WET_CODES)
        stype = cols.session_type_name(int(sess["m_sessionType"]))
        baseline = self._player_setup()
        settled = engineer_log.settled_for(track, self.root) if self.root is not None else {}
        fuel_k, deg = self.engineer_models(track)
        confidence = self._generator_confidence(track)
        with self._eng_lock:
            if self.duel.active:
                raise EngineerError("A setup duel is running: stop it first")
            self.engineer.on_tyre_sets(self._tyre_sets())
            view = self.engineer.start(program, baseline, track, stype, wet, s.last_t, minutes,
                                       int(sess["m_sessionTimeLeft"]) or None, settled, fuel_k, deg,
                                       confidence)
            self._eng_saved = False
            self._eng_pump()
        return view

    def engineer_command(self, name: str, *args, **kwargs) -> dict:
        """Run an Engineer command (answer, confirm, skip, next_phase, revert, stop) and return the new view."""
        with self._eng_lock:
            view = getattr(self.engineer, name)(*args, **kwargs)
            self._eng_pump()
        return view

    def _engineer_view(self) -> dict | None:
        with self._eng_lock:
            return self.engineer.view() if self.engineer.phase != "idle" else None

    # -- setup duel adapter (same shape as the engineer's) -------------------------------------
    def duel_start(self, n: int, names: list[str] | None = None) -> dict:
        s = self.s
        sess, lapd, stat = s.get(PID_SESSION), s.get(PID_LAP), s.get(PID_STATUS)
        if sess is None or lapd is None:
            raise EngineerError("No live session data yet")
        track = cols.track_name(int(sess["m_trackId"]))
        comp = int(stat["m_carStatusData"][s.player]["m_actualTyreCompound"]) if stat is not None else None
        wet = int(sess["m_weather"]) >= 3 or (comp is not None and comp in compounds.WET_CODES)
        stype = cols.session_type_name(int(sess["m_sessionType"]))
        fuel_k, deg = self.engineer_models(track)
        with self._eng_lock:
            if self.engineer.active:
                raise EngineerError("The engineer is running: stop it first")
            self.duel.on_tyre_sets(self._tyre_sets())
            view = self.duel.start(n, names, track, stype, wet, s.last_t, int(sess["m_sessionTimeLeft"]) or None,
                                   fuel_k, deg)
            self._duel_saved = False
            self._eng_pump()
        return view

    def duel_command(self, name: str, *args, **kwargs) -> dict:
        """Run a Duel command (rank, confirm, skip_contestant, stop) and return the new view. The tyre model for the
        ranking is built before taking the lock (it is slow)."""
        if name == "rank":
            with self._eng_lock:
                compound, track = self.duel.compound, self.duel.track
            plan_time, race_laps = self._duel_plan(track, compound)
            kwargs = {**kwargs, "plan_time": plan_time, "race_laps": race_laps}
        with self._eng_lock:
            view = getattr(self.duel, name)(*args, **kwargs)
            self._eng_pump()
        return view

    def _duel_plan(self, track: str, compound: int | None):
        if self.root is None or not track:
            return None, None
        try:
            from .. import duel_library

            plan_time, race_laps, _ = duel_library.wear_plan_time(duel_library.track_name(track), "dry", compound, self.root)
            return plan_time, race_laps
        except Exception:
            log.exception("duel: no tyre model for %s", track)
            return None, None

    def _duel_view(self) -> dict | None:
        with self._eng_lock:
            return self.duel.view() if self.duel.phase != "idle" else None

    def _lap_valid(self, lap: int) -> bool:
        hist = self.s.history.get(self.s.player)
        try:
            if hist is None or lap < 1 or lap > 100:
                return True
            return bool(int(hist["m_lapHistoryData"][lap - 1]["m_lapValidBitFlags"]) & 1)
        except Exception:
            return True

    # -- snapshot -----------------------------------------------------------------------------
    def snapshot(self) -> dict | None:
        s = self.s
        lapd, sess, tele, stat = s.get(PID_LAP), s.get(PID_SESSION), s.get(PID_TELEMETRY), s.get(PID_STATUS)
        if lapd is None or sess is None or tele is None or stat is None:
            return None
        p = s.player
        me = lapd["m_lapData"][p]
        out: dict[str, Any] = {"type": "snapshot", "t": s.last_t}
        out["session"] = self._session(sess, me)
        out["timing"] = self._timing(me)
        out["tyres"] = self._tyres(tele["m_carTelemetryData"][p], stat["m_carStatusData"][p], p)
        out["fuel"] = self._fuel(stat["m_carStatusData"][p], sess, me)
        out["ers"] = self._ers(stat["m_carStatusData"][p], p)
        out["damage"] = self._damage(sess, me)
        out["rivals"] = self._rivals(lapd, sess)
        out["strategy"] = self.strategy
        out["engineer"] = self._engineer_view()
        out["duel"] = self._duel_view()
        return out

    def _session(self, sess, me) -> dict:
        track = cols.track_name(int(sess["m_trackId"]))
        fc = []
        for f in sess["m_weatherForecastSamples"][: int(sess["m_numWeatherForecastSamples"])][:6]:
            fc.append({"in_min": int(f["m_timeOffset"]), "weather": WEATHER[min(int(f["m_weather"]), 5)],
                       "rain_pct": int(f["m_rainPercentage"])})
        ideal, latest = int(sess["m_pitStopWindowIdealLap"]), int(sess["m_pitStopWindowLatestLap"])
        sc = int(sess["m_safetyCarStatus"])
        return {
            "track": track, "type": cols.session_type_name(int(sess["m_sessionType"])) or "Session",
            "lap": int(me["m_currentLapNum"]), "total_laps": int(sess["m_totalLaps"]),
            "position": int(me["m_carPosition"]),
            "weather": WEATHER[min(int(sess["m_weather"]), 5)], "track_temp": int(sess["m_trackTemperature"]),
            "air_temp": int(sess["m_airTemperature"]), "sc": sc, "sc_name": SC_NAMES[min(sc, 3)],
            "forecast": fc, "game_pit_window": [ideal, latest] if ideal else None,
            "time_left_s": int(sess["m_sessionTimeLeft"]), "pit_status": int(me["m_pitStatus"]),
            "penalties_s": int(me["m_penalties"]),
        }

    def _timing(self, me) -> dict:
        cur = int(me["m_currentLapTimeInMS"]) / 1000.0
        d = float(me["m_lapDistance"])
        running = d > 20 and cur > 0

        def delta(ref: RefLap | None) -> float | None:
            return cur - ref.at(d) if (ref is not None and running) else None

        d_best, d_last = delta(self.sess_ref), delta(self.last_ref)
        s1 = _ms(me["m_sector1TimeInMSPart"], me["m_sector1TimeMinutesPart"])
        s2 = _ms(me["m_sector2TimeInMSPart"], me["m_sector2TimeMinutesPart"])
        last = int(me["m_lastLapTimeInMS"]) / 1000.0
        return {
            "lap_time": cur, "last": last or None,
            "best": self.sess_ref.total if self.sess_ref else None,
            "best_lap": self.sess_ref.lap if self.sess_ref else None,
            "sectors": [s1 or None, s2 or None], "sector": int(me["m_sector"]) + 1,
            "delta_best": d_best, "delta_last": d_last,
            "predicted": (self.sess_ref.total + d_best) if d_best is not None else
                         ((self.last_ref.total + d_last) if d_last is not None else None),
            "lap_distance": d, "invalid": bool(int(me["m_currentLapInvalid"])),
        }

    def _tyres(self, tel, status, p: int) -> dict:
        comp = int(status["m_actualTyreCompound"])
        surf_t = self._targets(comp, "surface")
        inner_t = self._targets(comp, "inner")
        damage = self.s.get(PID_DAMAGE)
        dmg = damage["m_carDamageData"][p] if damage is not None else None
        if self._wear_limit is None:
            try:
                from ..api.tyres import default_limit

                self._wear_limit = float(default_limit(self.root))
            except Exception:
                self._wear_limit = float(tyres.WEAR_LIMIT_PCT)
        limit = self._wear_limit
        wheels = {}
        for i, name in enumerate(WHEELS):
            surf, inner = int(tel["m_tyresSurfaceTemperature"][i]), int(tel["m_tyresInnerTemperature"][i])
            wear = float(dmg["m_tyresWear"][i]) if dmg is not None else None
            wheels[name] = {
                "surface": surf, "inner": inner, "press_psi": round(float(tel["m_tyresPressure"][i]), 2),
                "wear": wear, "damage": int(dmg["m_tyresDamage"][i]) if dmg is not None else None,
                "blister": int(dmg["m_tyreBlisters"][i]) if dmg is not None else None,
                "brake_temp": int(tel["m_brakesTemperature"][i]),
                "brake_damage": int(dmg["m_brakesDamage"][i]) if dmg is not None else None,
                "status": _window(surf, surf_t.temp_lo, surf_t.temp_hi),
                "inner_status": _window(inner, inner_t.temp_lo, inner_t.temp_hi),
                "wear_status": ("limit" if wear is not None and wear >= limit else
                                "high" if wear is not None and wear >= 0.8 * limit else "ok"),
            }
        return {"compound": comp, "label": compounds.c_label(comp), "age": int(status["m_tyresAgeLaps"]),
                "wear_limit": limit, "wheels": wheels,
                "targets": {"surface": [surf_t.temp_lo, surf_t.temp_hi], "inner": [inner_t.temp_lo, inner_t.temp_hi]}}

    def _fuel(self, status, sess, me) -> dict:
        kg = float(status["m_fuelInTank"])
        recent = self._fuel_per_lap[-FUEL_LAPS_WINDOW:]
        per_lap = float(np.median(recent)) if recent else None
        total, lap = int(sess["m_totalLaps"]), int(me["m_currentLapNum"])
        left_race = max(0.0, total - lap + 1 - float(me["m_lapDistance"]) / max(float(sess["m_trackLength"]), 1.0)) if total else None
        laps_left = kg / per_lap if per_lap else None
        return {
            "kg": kg, "capacity": float(status["m_fuelCapacity"]), "per_lap": per_lap, "laps_left": laps_left,
            "margin_laps": (laps_left - left_race) if (laps_left is not None and left_race is not None) else None,
            "game_laps_left": float(status["m_fuelRemainingLaps"]), "mix": int(status["m_fuelMix"]),
        }

    def _ers(self, status, p: int) -> dict:
        t2 = self.s.get(PID_TELEMETRY2)
        c2 = t2["m_carTelemetryData2"][p] if t2 is not None else None
        return {
            "store_mj": float(status["m_ersStoreEnergy"]) / 1e6, "mode": int(status["m_ersDeployMode"]),
            "deployed_mj": float(status["m_ersDeployedThisLap"]) / 1e6,
            "harvested_mj": (float(status["m_ersHarvestedThisLapMGUK"]) + float(status["m_ersHarvestedThisLapMGUH"])) / 1e6,
            "harvest_limit_mj": float(status["m_ersHarvestLimitPerLap"]) / 1e6,
            "overtake": bool(c2["m_overtakeActive"]) if c2 is not None else None,
            "overtake_available": bool(c2["m_overtakeAvailable"]) if c2 is not None else None,
            "active_aero": int(c2["m_activeAeroMode"]) if c2 is not None else None,
        }

    def _damage(self, sess, me) -> dict | None:
        dmg = self.s.get(PID_DAMAGE)
        if dmg is None:
            return None
        c = dmg["m_carDamageData"][self.s.player]
        parts = [{"part": label, "group": group, "pct": int(c[f]), "hit_lap": self._hits.get(label)}
                 for f, label, group in DAMAGE_PARTS]
        wear = [{"part": label, "pct": int(c[f])} for f, label in WEAR_PARTS]
        faults = [name for name, f in (("DRS", "m_drsFault"), ("ERS", "m_ersFault")) if int(c[f])]
        if int(c["m_engineBlown"]):
            faults.append("Engine blown")
        if int(c["m_engineSeized"]):
            faults.append("Engine seized")
        wing_pct = max(int(c["m_frontLeftWingDamage"]), int(c["m_frontRightWingDamage"]))
        hit_lap = max((self._hits[k] for k in ("Front wing L", "Front wing R") if k in self._hits), default=None)
        aero_hit = max((self._hits[p["part"]] for p in parts if p["group"] == "aero" and p["part"] in self._hits),
                       default=None)
        loss = damage_loss(self.history, aero_hit) if aero_hit is not None else None
        advice = {"call": None, "text": None}
        stype = cols.session_type_name(int(sess["m_sessionType"]))
        total = int(sess["m_totalLaps"])
        if stype == "Race" and total and hit_lap is not None:
            lap_now = int(me["m_currentLapNum"])
            st = self.strategy or {}
            window = st.get("box_window") if st.get("available") else None
            planned = window[0] if window and st.get("call") != "BOX" else None
            advice = wing_advice(wing_pct, loss, laps_left=max(0, total - lap_now + 1),
                                 pit_loss_s=float(st.get("pit_loss_s") or 22.0), wing_change_s=self.wing_change_s,
                                 planned_stop_lap=planned, lap_now=lap_now, sc=int(sess["m_safetyCarStatus"]) in (1, 2))
        non_wing_aero = [p for p in parts if p["group"] == "aero" and not p["part"].startswith("Front wing") and p["pct"] >= 10]
        return {
            "parts": parts, "wear": wear, "faults": faults, "front_wing_pct": wing_pct,
            "loss": loss, "advice": advice,
            "note": ("Only the front wing can be changed in a stop; " + ", ".join(p["part"] for p in non_wing_aero)
                     + " stays for the rest of the race.") if non_wing_aero else None,
            "any": any(p["pct"] > 0 for p in parts) or bool(faults),
        }

    def _rivals(self, lapd, sess, span: int = 5) -> list[dict]:
        stat = self.s.get(PID_STATUS)
        part = self.s.get(PID_PARTICIPANTS)
        dmg = self.s.get(PID_DAMAGE)
        cars = []
        for i in range(24):
            ld = lapd["m_lapData"][i]
            if int(ld["m_resultStatus"]) < 2 or int(ld["m_carPosition"]) == 0:
                continue
            cars.append((int(ld["m_carPosition"]), i, ld))
        cars.sort(key=lambda c: c[0])
        cum, acc = {}, 0.0
        for pos, i, ld in cars:
            acc += _ms(ld["m_deltaToCarInFrontInMSPart"], ld["m_deltaToCarInFrontInMinutesPart"])
            cum[i] = acc
        p = self.s.player
        if p not in cum:
            return []
        my_pos = next(pos for pos, i, _ in cars if i == p)
        my_stat = stat["m_carStatusData"][p] if stat is not None else None
        pit_loss = (self.strategy or {}).get("pit_loss_s") or 22.0
        out = []
        for pos, i, ld in cars:
            if abs(pos - my_pos) > span:
                continue
            st = stat["m_carStatusData"][i] if stat is not None else None
            name = _text(part["m_participants"][i]["m_name"]) if part is not None else f"Car {i}"
            gap = cum[i] - cum[p]
            comp = int(st["m_actualTyreCompound"]) if st is not None else None
            age = int(st["m_tyresAgeLaps"]) if st is not None else None
            wing = None
            if dmg is not None:
                cd = dmg["m_carDamageData"][i]
                wing = max(int(cd["m_frontLeftWingDamage"]), int(cd["m_frontRightWingDamage"]))
            row = {
                "pos": pos, "name": name or f"Car {i}", "you": i == p, "gap_s": gap,
                "compound": comp, "label": compounds.c_label(comp) if comp is not None else None, "age": age,
                "stops": int(ld["m_numPitStops"]), "last": int(ld["m_lastLapTimeInMS"]) / 1000.0 or None,
                "in_pit": int(ld["m_pitStatus"]) > 0, "threat": False, "wing_damage": wing,
            }
            # undercut threat: car just behind whose tyres are older than ours and who is within a pit stop's reach
            if (gap > 0 and my_stat is not None and age is not None and gap < min(pit_loss * 0.25, 6.0)
                    and age > int(my_stat["m_tyresAgeLaps"]) + 3):
                row["threat"] = True
            out.append(row)
        return out

    # -- strategy -----------------------------------------------------------------------------
    def update_strategy(self) -> None:
        """Heavy part (model build + DP). Call from a worker thread when ``strategy_dirty`` is set."""
        self.strategy_dirty = False
        s = self.s
        sess, lapd, stat = s.get(PID_SESSION), s.get(PID_LAP), s.get(PID_STATUS)
        if sess is None or lapd is None or stat is None:
            return
        stype = cols.session_type_name(int(sess["m_sessionType"]))
        total = int(sess["m_totalLaps"])
        if stype != "Race" or total <= 0:
            self.strategy = None
            return
        p = s.player
        me, st = lapd["m_lapData"][p], stat["m_carStatusData"][p]
        comp = int(st["m_actualTyreCompound"])
        track = normalize_track_name(cols.track_name(int(sess["m_trackId"]))) or cols.track_name(int(sess["m_trackId"]))
        if not compounds.is_slick(comp) or int(sess["m_weather"]) >= 3:
            self.strategy = {"available": False, "reason": "Wet running: no live dry-strategy call", "track": track}
            return
        try:
            from telemetry import strategy as strat

            from ..api.strategy import ParamsIn, build_inputs

            fpl = float(np.median(self._fuel_per_lap[-FUEL_LAPS_WINDOW:])) if self._fuel_per_lap else None
            pin = ParamsIn(laps=total, **({"fuel_per_lap_kg": fpl} if fpl else {}))
            inp = build_inputs(self.root or Path("."), track, "dry", pin)
            laps_done = int(me["m_currentLapNum"]) - 1
            age = int(st["m_tyresAgeLaps"])
            used = frozenset(self._used | {comp})
            plan = strat.plan_from_state(inp.specs, inp.params, lap=laps_done, compound=comp, age=age, used=used)
            if plan is None:
                in_model = any(sp.code == comp for sp in inp.specs)
                self.strategy = None if in_model else {
                    "available": False, "track": track, "pit_loss_s": inp.params.pit_loss_s,
                    "reason": f"{compounds.c_label(comp)} is not in the {track} compound model (set the track allocation or drive a library compound)"}
                return
            sc_now = int(sess["m_safetyCarStatus"])
            call = plan["call_sc"] if sc_now else plan["call_green"]
            out = {**plan, "available": True, "track": track, "pit_loss_s": inp.params.pit_loss_s,
                   "sc": sc_now, "call": call, "updated_lap": laps_done,
                   "compound": comp, "age": age, "model_sources": inp.model.sources}
            if call == "BOX" and self._call_prev != "BOX":
                self._emit("box", "Strategy: BOX" + (f" for {plan['fit_label']}" if plan.get("fit_label") else ""))
            self._call_prev = call
            self.strategy = out
        except Exception as exc:  # the live view must survive a missing model
            log.exception("live strategy failed")
            self.strategy = {"available": False, "reason": f"No model for {track}: {exc}", "track": track}


def _window(v: float, lo: float, hi: float) -> str:
    return "cold" if v < lo else "hot" if v > hi else "ok"
