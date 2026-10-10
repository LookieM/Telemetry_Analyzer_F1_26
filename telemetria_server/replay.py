"""Replay a raw capture as UDP datagrams, so the server, engine and UI run without the game.

Usage: python -m telemetria_server.replay FILE.f1cap [--speed 1] [--host 127.0.0.1] [--port 20777] [--start S]
"""

from __future__ import annotations

import argparse
import socket
import time

from .udp.capture_file import iter_capture


def replay(path: str, host: str = "127.0.0.1", port: int = 20777, speed: float = 1.0, start: float = 0.0,
           stop_event=None, quiet: bool = False) -> int:
    """Send the capture with its original timing divided by ``speed``. Returns packets sent."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sent = 0
    t0 = wall0 = None
    try:
        for t, data in iter_capture(path):
            if t0 is None:
                t0, wall0 = t, time.monotonic()
            rel = t - t0
            if rel < start:
                continue
            wait = (rel - start) / speed - (time.monotonic() - wall0)
            if wait > 0.002:
                time.sleep(wait)
            sock.sendto(data, (host, port))
            sent += 1
            if stop_event is not None and stop_event.is_set():
                break
            if not quiet and sent % 20000 == 0:
                print(f"{sent} packets, capture t={rel:.0f}s", flush=True)
    finally:
        sock.close()
    return sent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=20777)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--start", type=float, default=0.0, help="skip the first N seconds of the capture")
    a = ap.parse_args(argv)
    print(f"Replayed {replay(a.file, a.host, a.port, a.speed, a.start)} packets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
