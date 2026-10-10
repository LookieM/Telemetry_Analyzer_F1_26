"""Latest packet of every type plus frame-gap bookkeeping and the event log."""

from __future__ import annotations

import time
from collections import deque

from ..udp.parse import parse_packet

PID_MOTION, PID_SESSION, PID_LAP, PID_EVENT, PID_PARTICIPANTS = 0, 1, 2, 3, 4
PID_SETUP, PID_TELEMETRY, PID_STATUS, PID_DAMAGE, PID_HISTORY, PID_TYRESETS = 5, 6, 7, 10, 11, 12
PID_TELEMETRY2 = 16


class LiveState:
    def __init__(self) -> None:
        self.history: dict[int, object] = {}   # SessionHistory per car index
        self.pk: dict[int, object] = {}        # packet id -> latest body (record)
        self.header = None                      # latest header record
        self.uid: int | None = None
        self.player = 0
        self.packets = 0
        self.last_t = 0.0
        self.frame_gaps = 0
        self.frames = 0
        self._last_frame: int | None = None
        self._rate_t = time.monotonic()
        self._rate_n = 0
        self.rate = 0.0
        self.events: deque[dict] = deque(maxlen=200)
        self.new_session = False                # set when the session UID changes; the engine clears it

    def feed(self, data: bytes, t: float | None = None) -> int | None:
        parsed = parse_packet(data)
        if parsed is None:
            return None
        pid, rec = parsed
        h = rec["header"]
        uid = int(h["m_sessionUID"])
        if uid == 0:
            return None  # menus / results screen: not a session, must not reset the live state
        if uid != self.uid:
            self.uid = uid
            self.pk.clear()
            self.history.clear()
            self._last_frame = None
            self.new_session = True
        self.header = h
        self.player = int(h["m_playerCarIndex"])
        self.packets += 1
        self.last_t = t if t is not None else time.time()
        if pid == PID_LAP:  # one frame-id per tick, count gaps once per tick
            f = int(h["m_frameIdentifier"])
            if self._last_frame is not None and f > self._last_frame:
                self.frames += 1
                self.frame_gaps += max(0, f - self._last_frame - 1)
            self._last_frame = f
        self._rate_n += 1
        now = time.monotonic()
        if now - self._rate_t >= 1.0:
            self.rate = self._rate_n / (now - self._rate_t)
            self._rate_n, self._rate_t = 0, now
        if pid == PID_HISTORY:
            self.history[int(rec["body"]["m_carIdx"])] = rec["body"]
        self.pk[pid] = rec["body"]
        return pid

    @property
    def gap_pct(self) -> float:
        tot = self.frames + self.frame_gaps
        return 100.0 * self.frame_gaps / tot if tot else 0.0

    def get(self, pid: int):
        return self.pk.get(pid)
