"""Record the player's laps from UDP packets into an SRT-style 1 m binned frame, then ingest it."""

from __future__ import annotations

import hashlib
import json
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
    type; the last sample in each (lap, 1 m bin) wins. Like SRT, only samples on a running lap are
    kept: nothing from the garage or while the lap timer stands at 0 (grid, refuel, pit-lane exit
    before the line). When the lap timer jumps back (flashback, restart) the bins recorded "in the
    future" of the new time are dropped, so a rewound lap is redriven instead of mixing two attempts.
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
        self._last_t: dict[int, float] = {}

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
                "driver_status": int(lap["m_driverStatus"]),
            }
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
        t_lap = raw["lap_time_ms"] / 1000.0
        if raw.get("driver_status", 1) == 0 or t_lap <= 0.0:
            return False  # in the garage, or the lap timer is not running
        if self._cur_lap is not None and lap < self._cur_lap:
            for later in [n for n in self._laps if n > lap]:
                self._laps.pop(later)  # rewound into an earlier lap
        if lap in self._laps and t_lap < self._last_t.get(lap, 0.0) - 0.25:
            bins = self._laps[lap]
            for b in [b for b, r in bins.items() if r["lap_time"] > t_lap]:
                del bins[b]  # rewound within the lap: drop what was recorded after the new time
        self._last_t[lap] = t_lap
        self._cur_lap = lap
        row: dict[str, float] = {}
        for key in ("session", "setup", "status", "damage", "motion_ex", "telemetry2", "lap", "motion", "telemetry"):
            row.update(self._ctx.get(key, {}))
        row["lap_distance"] = dist
        row["lap_time"] = t_lap
        row["lap_number"] = lap
        row["lapNum"] = lap
        self._laps.setdefault(lap, {})[int(dist)] = row
        return True

    # -- output -------------------------------------------------------------------------------
    @property
    def has_data(self) -> bool:
        return any(len(v) > 30 for v in self._laps.values())

    def snapshot(self) -> dict[int, dict[int, dict]]:
        """Cheap copy of the recorded bins, safe to hand to a worker thread while feeding continues."""
        return {lap: dict(bins) for lap, bins in self._laps.items()}

    def lap_frame(self, lap: int) -> pd.DataFrame:
        """SRT-style frame of one recorded lap (0-based recorder lap = game lap number - 1); empty if unknown."""
        bins = self._laps.get(lap)
        return self.build_frame({lap: dict(bins)}) if bins else pd.DataFrame()

    def build_frame(self, laps: dict[int, dict[int, dict]] | None = None) -> pd.DataFrame:
        """SRT-style frame: per lap, 1 m bins from first to last observed bin, gaps interpolated."""
        laps = self._laps if laps is None else laps
        parts = []
        for lap in sorted(laps):
            bins = laps[lap]
            if len(bins) < 10:
                continue
            df = pd.DataFrame.from_dict(bins, orient="index").sort_index()
            # integer channels (positions, counters, flags, modes) are carried forward, never interpolated
            is_cat = [c in _CATEGORICAL or "_setup" in c or pd.api.types.is_integer_dtype(df[c]) for c in df.columns]
            full = np.arange(int(df.index.min()), int(df.index.max()) + 1)
            df = df.reindex(full)
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

    def checkpoint(self, live_dir: Path, laps: dict[int, dict[int, dict]] | None = None) -> Path | None:
        """Write the frame so far (plus a JSON sidecar) to ``live_dir``; survives a crash mid-session."""
        df = self.build_frame(laps)
        if df.empty:
            return None
        live_dir.mkdir(parents=True, exist_ok=True)
        base = live_dir / f"{self.session_uid}"
        tmp = base.with_suffix(".parquet.tmp")
        df.to_parquet(tmp, index=False)
        meta = {"hash": self.source_hash(), "session_type": self.session_type, "name": time.strftime("live-%Y%m%d-%H%M%S")}
        base.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
        tmp.replace(base.with_suffix(".parquet"))
        return base.with_suffix(".parquet")

    def discard_checkpoint(self, live_dir: Path) -> None:
        for ext in (".parquet", ".json", ".parquet.tmp"):
            (live_dir / f"{self.session_uid}{ext}").unlink(missing_ok=True)

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


def recover_checkpoints(live_dir: Path, app_root: Path | None = None) -> list:
    """Ingest sessions left in ``live_dir`` by a crashed run, then delete them. Returns the ImportResults."""
    from telemetry.import_session import ingest_dataframe
    from telemetry.loader import normalize_frame

    results = []
    for pq in sorted(live_dir.glob("*.parquet")) if live_dir.is_dir() else []:
        side = pq.with_suffix(".json")
        try:
            meta = json.loads(side.read_text(encoding="utf-8"))
            df = normalize_frame(pd.read_parquet(pq))
            results.append(ingest_dataframe(
                df, source_name=meta["name"] + "-recovered", source_hash=meta["hash"], original_size=0,
                app_root=app_root, session_type=cols.session_type_name(meta.get("session_type", 0)),
            ))
        except Exception:
            continue  # keep the file for a later attempt / manual inspection
        pq.unlink(missing_ok=True)
        side.unlink(missing_ok=True)
    for tmp in live_dir.glob("*.tmp") if live_dir.is_dir() else []:
        tmp.unlink(missing_ok=True)
    return results
