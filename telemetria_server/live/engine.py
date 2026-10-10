"""LiveEngine: turns the latest packets into the 10 Hz snapshot, events and the live strategy call."""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from telemetry import compounds, db, tyres
from telemetry.corners import normalize_track_name

from ..udp import srt_columns as cols
from ..udp import structs
from .state import (PID_DAMAGE, PID_EVENT, PID_HISTORY, PID_LAP, PID_PARTICIPANTS, PID_SESSION, PID_STATUS,
                    PID_TELEMETRY, PID_TELEMETRY2, LiveState)

log = logging.getLogger("telemetria.live")

WHEELS = ("RL", "RR", "FL", "FR")  # UDP array order
WEATHER = ("Clear", "Light cloud", "Overcast", "Light rain", "Heavy rain", "Storm")
SC_NAMES = ("", "SC", "VSC", "formation")
EVENT_DETAIL = {"PENA": "Penalty", "FTLP": "FastestLap", "RTMT": "Retirement", "SCAR": "SafetyCar",
                "SPTP": "SpeedTrap", "OVTK": "Overtake", "COLL": "Collision"}
FUEL_LAPS_WINDOW = 3


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

    def at(self, d: float) -> float:
        return float(np.interp(d, self.dist, self.time))


class LiveEngine:
    def __init__(self, state: LiveState, app_root: Path | None = None) -> None:
        self.s = state
        self.root = app_root
        self.ref_mode = "pb"                # "pb" (library best on this track) or "session"
        self.pb_ref: RefLap | None = None
        self.sess_ref: RefLap | None = None
        self._pb_track: str | None = None
        self._cur_d: list[float] = []
        self._cur_t: list[float] = []
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
        self._strategy_ctx: Any = None
        self._call_prev: str | None = None
        self._target_cache: dict[tuple, Any] = {}
        self._best_ms: int | None = None
        self._wear_limit: float | None = None
        self._track_len = 0.0

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
        self.sess_ref = None
        self._cur_d, self._cur_t = [], []
        self._lap_num = None
        self._fuel_at_lap.clear()
        self._fuel_per_lap.clear()
        self._used.clear()
        self.strategy = None
        self._strategy_ctx = None
        self._call_prev = None
        self._best_ms = None
        self._pit_prev = self._sc_prev = 0
        self._baselined = False
        self.s.new_session = False

    def _load_pb(self, track: str) -> None:
        self._pb_track = track
        self.pb_ref = None
        try:
            df = db.list_sessions(self.root, track=track)
            if df.empty or "best_lap_time" not in df.columns:
                return
            df = df[df["best_lap_time"].notna() & (df["best_lap_time"] > 20)]
            if df.empty:
                return
            row = df.sort_values("best_lap_time").iloc[0]
            tel = db.load_session_telemetry(int(row["id"]), self.root, columns=["lap", "lap_distance", "lap_time"])
            lap = tel[tel["lap"] == int(row["best_lap"])].dropna()
            lap = lap.sort_values("lap_distance").drop_duplicates("lap_distance")
            if len(lap) < 50:
                return
            t = lap["lap_time"].to_numpy(float)
            t = t - t[0]  # laps that start from the grid carry the pre-start time; the delta must start at 0
            self.pb_ref = RefLap(lap["lap_distance"].to_numpy(float), t, float(t[-1]), "PB")
        except Exception:
            log.exception("could not load the personal-best reference lap")

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
            self._load_pb(normalize_track_name(track) or track)
            self.strategy_dirty = True  # warm the compound model before the first lap ends

        lap_num = int(me["m_currentLapNum"])
        dist = float(me["m_lapDistance"])
        cur_t = int(me["m_currentLapTimeInMS"]) / 1000.0
        status = s.get(7)
        if status is not None:
            fuel = float(status["m_carStatusData"][p]["m_fuelInTank"])
            self._fuel_at_lap.setdefault(lap_num, fuel)
            comp = int(status["m_carStatusData"][p]["m_actualTyreCompound"])
            if compounds.is_slick(comp):
                self._used.add(comp)
        if self._lap_num is None:
            self._lap_num = lap_num
        if lap_num != self._lap_num:
            self._on_new_lap(lap_num, me)
        if dist >= 0 and (not self._cur_d or dist > self._cur_d[-1] - 1e-6):
            self._cur_d.append(dist)
            self._cur_t.append(cur_t)

        pit = int(me["m_pitStatus"])
        self._track_len = float(sess["m_trackLength"])
        sc = int(sess["m_safetyCarStatus"])
        if not self._baselined:  # first reading of a session: remember, do not announce
            self._baselined = True
            self._pit_prev, self._sc_prev = pit, sc
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
        self._read_events()

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
            d = np.frombuffer(ev["m_eventDetails"].tobytes()[: structs.EventDetails_Penalty_DT.itemsize], dtype=structs.EventDetails_Penalty_DT)[0]
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
        # fuel burned on the lap just completed
        if prev in self._fuel_at_lap and lap_num in self._fuel_at_lap and lap_num == prev + 1:
            used = self._fuel_at_lap[prev] - self._fuel_at_lap[lap_num]
            if used > 0.05:
                self._fuel_per_lap.append(used)
        last_ms = int(me["m_lastLapTimeInMS"])
        d, t = np.array(self._cur_d), np.array(self._cur_t)
        if (last_ms > 20000 and len(d) > 100 and self._track_len
                and d.min() < 0.05 * self._track_len and d.max() > 0.95 * self._track_len
                and (t > 0.5).mean() > 0.95):  # the lap timer actually ran all lap
            d2, t2 = d.copy(), t.copy()
            t2[-1] = max(t2[-1], last_ms / 1000.0)
            valid = self._lap_valid(prev)
            if valid and (self.sess_ref is None or last_ms / 1000.0 < self.sess_ref.total):
                self.sess_ref = RefLap(d2, t2, last_ms / 1000.0, "session best")
        self._cur_d, self._cur_t = [], []
        self.strategy_dirty = True

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
        out["rivals"] = self._rivals(lapd, sess)
        out["strategy"] = self.strategy
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
        cur_ms = int(me["m_currentLapTimeInMS"])
        d = float(me["m_lapDistance"])
        ref = self.pb_ref if (self.ref_mode == "pb" and self.pb_ref) else self.sess_ref
        if ref is None:
            ref = self.pb_ref
        delta = predicted = None
        if ref is not None and d > 20:
            delta = cur_ms / 1000.0 - ref.at(d)
            predicted = ref.total + delta
        best = None
        hist = self.s.history.get(self.s.player)
        if hist is not None and int(hist["m_bestLapTimeLapNum"]):
            n = int(hist["m_bestLapTimeLapNum"])
            best = int(hist["m_lapHistoryData"][n - 1]["m_lapTimeInMS"]) / 1000.0
        s1 = _ms(me["m_sector1TimeInMSPart"], me["m_sector1TimeMinutesPart"])
        s2 = _ms(me["m_sector2TimeInMSPart"], me["m_sector2TimeMinutesPart"])
        last = int(me["m_lastLapTimeInMS"]) / 1000.0
        return {
            "lap_time": cur_ms / 1000.0, "last": last or None, "best": best,
            "sectors": [s1 or None, s2 or None], "sector": int(me["m_sector"]) + 1,
            "delta": delta, "predicted": predicted, "ref": ref.label if ref else None,
            "ref_time": ref.total if ref else None, "lap_distance": d,
            "invalid": bool(int(me["m_currentLapInvalid"])),
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

    def _rivals(self, lapd, sess, span: int = 5) -> list[dict]:
        stat = self.s.get(PID_STATUS)
        part = self.s.get(PID_PARTICIPANTS)
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
            row = {
                "pos": pos, "name": name or f"Car {i}", "you": i == p, "gap_s": gap,
                "compound": comp, "label": compounds.c_label(comp) if comp is not None else None, "age": age,
                "stops": int(ld["m_numPitStops"]), "last": int(ld["m_lastLapTimeInMS"]) / 1000.0 or None,
                "in_pit": int(ld["m_pitStatus"]) > 0, "threat": False,
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
                    "available": False, "track": track,
                    "reason": f"{compounds.c_label(comp)} is not in the {track} compound model (set the track allocation or drive a library compound)"}
                return
            sc_now = int(sess["m_safetyCarStatus"])
            call = plan["call_sc"] if sc_now else plan["call_green"]
            specs = {sp.code: sp for sp in inp.specs}
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
