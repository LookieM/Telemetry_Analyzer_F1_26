"""Live UDP ingest: receive datagrams, optionally forward them, record sessions and ingest them at the end."""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from pathlib import Path

from .config import Config
from .udp.recorder import SESSION_IDLE_S, SessionRecorder

log = logging.getLogger("telemetria.ingest")
EVENT_SEND = b"SEND"


class SessionManager:
    """Synchronous core (testable without sockets): feed datagrams, call ``tick`` for the idle timeout.

    A session ends on a new ``m_sessionUID``, the ``SEND`` event, or ``idle_s`` of silence. Finished
    recorders are returned/handed to ``on_finish`` (which ingests them off the event loop).
    """

    def __init__(self, on_finish=None, idle_s: float = SESSION_IDLE_S) -> None:
        self.rec = SessionRecorder()
        self.on_finish = on_finish
        self.idle_s = idle_s
        self.finished: list[SessionRecorder] = []
        self.packets = 0
        self.last_lap_seen: int | None = None

    def _finish(self) -> None:
        rec, self.rec = self.rec, SessionRecorder()
        if rec.has_data:
            self.finished.append(rec)
            if self.on_finish:
                self.on_finish(rec)

    def feed(self, data: bytes, t: float | None = None) -> None:
        self.packets += 1
        if self.rec.is_new_session(data):
            self._finish()
        self.rec.feed(data, t)
        if len(data) == 45 and data[29:33] == EVENT_SEND:
            self._finish()

    def tick(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        if self.rec.session_uid is not None and now - self.rec.last_packet_t > self.idle_s:
            self._finish()

    def close(self) -> None:
        self._finish()


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self, mgr: SessionManager, forward: tuple[str, int] | None) -> None:
        self.mgr = mgr
        self.forward = forward
        self.transport: asyncio.DatagramTransport | None = None
        self.fwd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if forward else None

    def connection_made(self, transport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        if self.fwd_sock is not None:
            try:
                self.fwd_sock.sendto(data, self.forward)
            except OSError:
                pass
        try:
            self.mgr.feed(data, time.time())
        except Exception:  # never let a bad packet kill the socket
            log.exception("ingest failed for one packet")


def _hostport(text: str) -> tuple[str, int] | None:
    host, _, port = text.rpartition(":")
    return (host, int(port)) if host and port.isdigit() else None


class UdpIngest:
    """Binds the UDP port inside the running loop; ingests finished sessions in a worker thread."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.loop: asyncio.AbstractEventLoop | None = None
        self.mgr = SessionManager(self._queue_ingest)
        self.transport = None
        self.protocol: _Protocol | None = None
        self.results: list = []
        self._tasks: set[asyncio.Task] = set()
        self._ticker: asyncio.Task | None = None

    async def start(self) -> bool:
        self.loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            sock.bind((self.cfg.host if self.cfg.host != "0.0.0.0" else "0.0.0.0", self.cfg.udp_port))
        except OSError as exc:
            sock.close()
            log.warning("UDP port %s unavailable (%s); live recording disabled", self.cfg.udp_port, exc)
            return False
        fwd = _hostport(self.cfg.forward_to) if self.cfg.forward_to else None
        self.protocol = _Protocol(self.mgr, fwd)
        self.transport, _ = await self.loop.create_datagram_endpoint(lambda: self.protocol, sock=sock)
        self._ticker = asyncio.create_task(self._tick_loop())
        log.info("listening for F1 UDP on %s:%s", self.cfg.host, self.cfg.udp_port)
        return True

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            self.mgr.tick()

    def _queue_ingest(self, rec: SessionRecorder) -> None:
        assert self.loop is not None
        task = self.loop.create_task(self._ingest(rec))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _ingest(self, rec: SessionRecorder) -> None:
        try:
            res = await asyncio.to_thread(rec.ingest, self.cfg.app_root)
            self.results.append(res)
            log.info("recorded session: %s", res.message)
        except Exception:
            log.exception("could not ingest the recorded session")

    async def stop(self) -> None:
        if self._ticker:
            self._ticker.cancel()
        if self.transport:
            self.transport.close()
        if self.protocol and self.protocol.fwd_sock:
            self.protocol.fwd_sock.close()
        self.mgr.close()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
