"""Record the player's laps from UDP packets into an SRT-style 1 m binned frame, then ingest it."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import srt_columns as cols
from .parse import parse_packet

SESSION_IDLE_S = 60.0
_CATEGORICAL = {
    "gear", "drs", "pit_status", "race_position", "tyre_compound_0", "tyre_compound_1", "tyre_compound_2",
    "tyre_compound_3", "tyres_age", "ers_deployMode", "weather", "safetyCarStatus", "pit_limiter",
    "fuel_type", "flags_status", "activeAero_mode", "activeAero_allowed", "overtake", "overtake_allowed",
    "drs_allowed", "terrain_0", "terrain_1", "terrain_2", "terrain_3", "penalties", "warnings",
}


class SessionRecorder:
    """Feed raw datagrams with :meth:`feed`; call :meth:`build_frame` or :meth:`ingest` at the end.

    Samples are taken on every CarTelemetry packet and combined with the latest packet of every other
    type; the last sample in each (lap, 1 m bin) wins. A flashback drops the lap being redone.
    """

    def __init__(self) -> None:
        self.session_uid: int | None = None
        self.player: int | None = None
        self.track_id: int | None = None
        self.track_length: float = 0.0
        self.session_type: int = 0
        self.last_packet_t: float = 0.0
        self.packets = 0
        self._ctx: dict[str, dict] = {}
        self._laps: dict[int, dict[int, dict]] = {}
        self._cur_lap: int | None = None

    # -- ingest -------------------------------------------------------------------------------
    def is_new_session(self, data: bytes) -> bool:
        if len(data) < 15 or self.session_uid is None:
            return False
        return int.from_bytes(data[7:15], "little") != self.session_uid

    def feed(self, data: bytes, t: float | None = None) -> bool:
        """Consume one datagram. Returns True if a sample row was stored."""
        parsed = parse_packet(data)
        if parsed is None:
            return False
        pid, rec = parsed
        h = rec["header"]
        uid = int(h["m_sessionUID"])
        if self.session_uid is None:
            self.session_uid = uid
        elif uid != self.session_uid:
            return False  # the caller starts a new recorder (see is_new_session)
        self.last_packet_t = t if t is not None else time.time()
        self.packets += 1
        p = int(h["m_playerCarIndex"])
        self.player = p
        body = rec["body"]
        if pid == 0:
            self._ctx["motion"] = cols.motion_row(body["m_carMotionData"][p])
        elif pid == 1:
            self._ctx["session"] = cols.session_row(body)
            self.track_id = int(body["m_trackId"])
            self.track_length = float(body["m_trackLength"])
            self.session_type = int(body["m_sessionType"])
        elif pid == 2:
            lap = body["m_lapData"][p]
            self._ctx["lap"] = cols.lap_row(lap)
            self._ctx["lapraw"] = {
                "lap_distance": float(lap["m_lapDistance"]),
                "lap_time_ms": int(lap["m_currentLapTimeInMS"]),
                "lap_num": int(lap["m_currentLapNum"]),
            }
        elif pid == 3:
            if bytes(body["m_eventStringCode"]).decode("ascii", "ignore") == "FLBK":
                self._flashback = True
        elif pid == 5:
            self._ctx["setup"] = cols.setup_row(body["m_carSetups"][p])
        elif pid == 6:
            self._ctx["telemetry"] = cols.telemetry_row(body["m_carTelemetryData"][p])
            return self._sample()
        elif pid == 7:
            self._ctx["status"] = cols.status_row(body["m_carStatusData"][p])
        elif pid == 10:
            self._ctx["damage"] = cols.damage_row(body["m_carDamageData"][p])
        elif pid == 13:
            self._ctx["motion_ex"] = cols.motion_ex_row(body["m_carMotionEXData"])
        elif pid == 16:
            self._ctx["telemetry2"] = cols.telemetry2_row(body["m_carTelemetryData2"][p])
        return False

    _flashback = False

    # -- sampling -----------------------------------------------------------------------------
    def _sample(self) -> bool:
        raw = self._ctx.get("lapraw")
        if raw is None or "motion" not in self._ctx:
            return False
        lap = max(0, raw["lap_num"] - 1)
        dist = raw["lap_distance"]
        if not np.isfinite(dist) or dist < 0:
            return False
        if self.track_length and dist > self.track_length + 50:
            return False
        if self._flashback:
            # the game rewound: whatever we hold for the lap being (re)entered is stale
            self._flashback = False
            self._laps.pop(lap, None)
        elif self._cur_lap is not None and lap < self._cur_lap:
            self._laps.pop(lap, None)
        self._cur_lap = lap
        row: dict[str, float] = {}
        for key in ("session", "setup", "status", "damage", "motion_ex", "telemetry2", "lap", "motion", "telemetry"):
            row.update(self._ctx.get(key, {}))
        row["lap_distance"] = dist
        row["lap_time"] = raw["lap_time_ms"] / 1000.0
        row["lap_number"] = lap
        row["lapNum"] = lap
        self._laps.setdefault(lap, {})[int(dist)] = row
        return True

    # -- output -------------------------------------------------------------------------------
    @property
    def has_data(self) -> bool:
        return any(len(v) > 30 for v in self._laps.values())

    def build_frame(self) -> pd.DataFrame:
        """SRT-style frame: per lap, 1 m bins from first to last observed bin, gaps interpolated."""
        parts = []
        for lap in sorted(self._laps):
            bins = self._laps[lap]
            if len(bins) < 10:
                continue
            df = pd.DataFrame.from_dict(bins, orient="index").sort_index()
            full = np.arange(int(df.index.min()), int(df.index.max()) + 1)
            df = df.reindex(full)
            is_cat = [c in _CATEGORICAL or "_setup" in c for c in df.columns]
            cat = df.loc[:, is_cat].ffill()
            num = df.loc[:, [not x for x in is_cat]].interpolate(limit_area="inside")
            df = pd.concat([num, cat], axis=1).ffill()
            df = df.assign(bin_index=full, binIndex=full, validBin=1)
            parts.append(df)
        if not parts:
            return pd.DataFrame()
        out = pd.concat(parts, ignore_index=True).copy()
        track = cols.track_name(self.track_id if self.track_id is not None else -1)
        return out.assign(
            lap_number=out["lap_number"].astype(int), lapNum=out["lapNum"].astype(int),
            track=track, trackId=track, car="F1 26", trackLength=self.track_length,
            lapIndex=out["lap_number"].astype(int), lapFlag=0, lap_time_invalid=0,
        )

    def source_hash(self) -> str:
        return hashlib.sha256(f"udp:{self.session_uid}:{self.track_id}".encode()).hexdigest()

    def ingest(self, app_root: Path | None = None, *, source_name: str | None = None):
        from telemetry.import_session import ingest_dataframe
        from telemetry.loader import normalize_frame

        df = normalize_frame(self.build_frame())
        name = source_name or time.strftime("live-%Y%m%d-%H%M%S")
        return ingest_dataframe(
            df,
            source_name=name,
            source_hash=self.source_hash(),
            original_size=0,
            app_root=app_root,
            session_type=cols.session_type_name(self.session_type),
        )
