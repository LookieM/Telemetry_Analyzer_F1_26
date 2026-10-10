"""Live UDP ingest: receive datagrams, optionally forward them, record sessions and ingest them at the end."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
import socket
import time
from pathlib import Path

from .config import Config
from .serialization import to_jsonable
from .live.engine import LiveEngine
from .live.state import LiveState
from .udp.recorder import SESSION_IDLE_S, SessionRecorder, recover_checkpoints

log = logging.getLogger("telemetria.ingest")
EVENT_SEND = b"SEND"


class SessionManager:
    """Synchronous core (testable without sockets): feed datagrams, call ``tick`` for the idle timeout.

    A session ends on a new ``m_sessionUID``, the ``SEND`` event, or ``idle_s`` of silence. Finished
    recorders are returned/handed to ``on_finish`` (which ingests them off the event loop).
    """

    def __init__(self, on_finish=None, idle_s: float = SESSION_IDLE_S, on_lap=None) -> None:
        self.rec = SessionRecorder()
        self.on_finish = on_finish
        self.on_lap = on_lap  # called with (recorder, snapshot) when a new lap starts
        self.idle_s = idle_s
        self.finished: list[SessionRecorder] = []
        self.packets = 0
        self.last_lap_seen: int | None = None

    def _finish(self) -> None:
        rec, self.rec = self.rec, SessionRecorder()
        self.last_lap_seen = None
        if rec.has_data:
            self.finished.append(rec)
            if self.on_finish:
                self.on_finish(rec)

    def feed(self, data: bytes, t: float | None = None) -> None:
        self.packets += 1
        if len(data) >= 15 and int.from_bytes(data[7:15], "little") == 0:
            return  # menus / results screen: not a session (would otherwise split a recording)
        if self.rec.is_new_session(data):
            self._finish()
        self.rec.feed(data, t)
        cur = self.rec._cur_lap
        if cur != self.last_lap_seen:
            if self.on_lap and self.last_lap_seen is not None and cur is not None and cur > self.last_lap_seen:
                self.on_lap(self.rec, self.rec.snapshot())
            self.last_lap_seen = cur
        if len(data) == 45 and data[29:33] == EVENT_SEND:
            self._finish()

    def tick(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        if self.rec.session_uid is not None and now - self.rec.last_packet_t > self.idle_s:
            self._finish()

    def close(self) -> None:
        self._finish()


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self, mgr: SessionManager, forward: list[tuple[str, int]] | None, live: LiveState | None = None) -> None:
        self.mgr = mgr
        self.live = live
        self.forward = list(forward or [])
        self.transport: asyncio.DatagramTransport | None = None
        self.fwd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if self.forward else None

    def connection_made(self, transport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        if self.fwd_sock is not None:
            for target in self.forward:
                try:
                    self.fwd_sock.sendto(data, target)
                except OSError:
                    pass  # a closed target app must not stop the others
        now = time.time()
        try:
            if self.live is not None:
                self.live.feed(data, now)
            self.mgr.feed(data, now)
        except Exception:  # never let a bad packet kill the socket
            log.exception("ingest failed for one packet")


def _hostport(text: str) -> tuple[str, int] | None:
    host, _, port = text.strip().rpartition(":")
    return (host.strip(), int(port)) if host.strip() and port.isdigit() else None


LOCAL_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0"}


def udp_port_owner_free(port: int) -> bool:
    """True if no other app holds the UDP port. Windows lets a 127.0.0.1 bind coexist with another
    app's 0.0.0.0 bind (and then steals its packets), so both addresses are probed first."""
    if port == 0:
        return True
    for addr in ("0.0.0.0", "127.0.0.1"):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.bind((addr, port))
        except OSError:
            return False
        finally:
            probe.close()
    return True


def forward_targets(spec: str | list[str], listen_port: int) -> list[tuple[str, int]]:
    """Parse ``"host:port, host:port"`` (or a list); drops invalid entries and our own port (a relay loop)."""
    items = spec if isinstance(spec, list) else str(spec or "").split(",")
    out: list[tuple[str, int]] = []
    for item in items:
        if not str(item).strip():
            continue
        hp = _hostport(str(item))
        if hp is None:
            log.warning("ignoring forward target %r (expected host:port)", item)
        elif hp[1] == listen_port and hp[0] in LOCAL_HOSTS:
            log.warning("ignoring forward target %s:%s: that is our own UDP port", *hp)
        elif hp not in out:
            out.append(hp)
    return out


class UdpIngest:
    """Binds the UDP port inside the running loop; ingests finished sessions in a worker thread."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.loop: asyncio.AbstractEventLoop | None = None
        self.live = LiveState()
        self.engine = LiveEngine(self.live, cfg.app_root, wing_change_s=cfg.wing_change_s)
        self.clients: set[asyncio.Queue] = set()
        self.recent_events: deque[dict] = deque(maxlen=12)  # replayed to a client that connects late
        self.mgr = SessionManager(self._queue_ingest, on_lap=self._queue_checkpoint)
        self.live_dir = cfg.app_root / "data" / "live"
        self.transport = None
        self.protocol: _Protocol | None = None
        self.results: list = []
        self._tasks: set[asyncio.Task] = set()
        self._ticker: asyncio.Task | None = None
        self._checkpointing = False
        self.udp_error: str | None = None

    async def start(self) -> bool:
        self.loop = asyncio.get_running_loop()
        try:
            for res in await asyncio.to_thread(recover_checkpoints, self.live_dir, self.cfg.app_root):
                log.info("recovered an interrupted session: %s", res.message)
        except Exception:
            log.exception("checkpoint recovery failed")
        self.udp_error = None
        if not udp_port_owner_free(self.cfg.udp_port):
            self.udp_error = (f"UDP port {self.cfg.udp_port} is already used by another app (SimHub? SRT? another "
                              f"copy of this server). Live view and recording are OFF. Move that app to another "
                              f"port and add it to forward_to, or start with --udp-port <free port>.")
            log.warning(self.udp_error)
            return False
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            sock.bind((self.cfg.host if self.cfg.host != "0.0.0.0" else "0.0.0.0", self.cfg.udp_port))
        except OSError as exc:
            sock.close()
            self.udp_error = f"UDP port {self.cfg.udp_port} unavailable ({exc}); live view and recording are OFF."
            log.warning(self.udp_error)
            return False
        fwd = forward_targets(self.cfg.forward_to, self.cfg.udp_port)
        self.protocol = _Protocol(self.mgr, fwd, self.live)
        self.transport, _ = await self.loop.create_datagram_endpoint(lambda: self.protocol, sock=sock)
        self._ticker = asyncio.create_task(self._tick_loop())
        self._live_task = asyncio.create_task(self._live_loop())
        log.info("Listening for F1 UDP on %s:%s", self.cfg.host, self.cfg.udp_port)
        log.info("Forwarding every packet to: %s", ", ".join(f"{h}:{p}" for h, p in fwd) if fwd else "nobody (forward_to is empty)")
        return True

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            self.mgr.tick()

    async def _live_loop(self) -> None:
        """Snapshot at ``live_rate_hz``; events and status go to every websocket client's queue."""
        period = 1.0 / max(1, self.cfg.live_rate_hz)
        last_status = 0.0
        strat_task: asyncio.Task | None = None
        while True:
            await asyncio.sleep(period)
            try:
                self.engine.tick()
                if self.engine.game_tyres_pending is not None:
                    payload, self.engine.game_tyres_pending = self.engine.game_tyres_pending, None
                    self._spawn(self._store_game_tyres(payload))
                if self.engine.strategy_dirty and (strat_task is None or strat_task.done()):
                    strat_task = asyncio.create_task(asyncio.to_thread(self.engine.update_strategy))
                msgs = self.engine.pop_events()
                self.recent_events.extend(msgs)
                snap = self.engine.snapshot() if self.clients else None
                if snap is not None:
                    msgs.append(snap)
                now = time.monotonic()
                if self.clients and now - last_status >= 1.0:
                    last_status = now
                    msgs.append(self.status())
                msgs = [to_jsonable(m) for m in msgs] if self.clients else []
                for q in list(self.clients):
                    for m in msgs:
                        if q.full():
                            q.get_nowait()  # slow client: drop the oldest instead of growing
                        q.put_nowait(m)
            except Exception:
                log.exception("live loop error")

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _store_game_tyres(self, payload: dict) -> None:
        from telemetry.compounds import save_game_tyres

        try:
            saved = await asyncio.to_thread(
                save_game_tyres, payload["track"], payload["sets"], total_laps=payload["total_laps"],
                session_type=payload["session_type"], app_root=self.cfg.app_root)
            if saved:
                log.info("Game tyre data stored for %s: %s", payload["track"],
                         ", ".join(f"{v['role']}={k}" for k, v in sorted(saved.items()) if v["role"] in ("S", "M", "H")))
                self.engine.strategy_dirty = True  # allocation / priors may have changed
        except Exception:
            log.exception("could not store the game tyre data")

    def status(self) -> dict:
        s = self.live
        return {
            "type": "status", "connected": bool(s.packets) and time.time() - s.last_t < 3.0,
            "packets_per_s": round(s.rate, 1), "frame_gap_pct": round(s.gap_pct, 3),
            "packets": s.packets, "recording": self.mgr.rec.has_data, "udp_error": self.udp_error,
        }

    def _queue_ingest(self, rec: SessionRecorder) -> None:
        assert self.loop is not None
        task = self.loop.create_task(self._ingest(rec))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _queue_checkpoint(self, rec: SessionRecorder, snap: dict) -> None:
        assert self.loop is not None
        if self._checkpointing:
            return  # a previous write is still running; the next lap will catch up
        self._checkpointing = True
        task = self.loop.create_task(self._checkpoint(rec, snap))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _checkpoint(self, rec: SessionRecorder, snap: dict) -> None:
        try:
            await asyncio.to_thread(rec.checkpoint, self.live_dir, snap)
        except Exception:
            log.exception("checkpoint write failed")
        finally:
            self._checkpointing = False

    async def _ingest(self, rec: SessionRecorder) -> None:
        try:
            res = await asyncio.to_thread(rec.ingest, self.cfg.app_root)
            await asyncio.to_thread(rec.discard_checkpoint, self.live_dir)
            self.results.append(res)
            log.info("recorded session: %s", res.message)
        except Exception:
            log.exception("could not ingest the recorded session")

    async def stop(self) -> None:
        if self._ticker:
            self._ticker.cancel()
        if getattr(self, "_live_task", None):
            self._live_task.cancel()
        if self.transport:
            self.transport.close()
        if self.protocol and self.protocol.fwd_sock:
            self.protocol.fwd_sock.close()
        self.mgr.close()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
