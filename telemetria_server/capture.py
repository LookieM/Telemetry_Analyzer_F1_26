"""Record raw F1 UDP telemetry to a file, optionally forwarding it unchanged.

Usage: python -m telemetria_server.capture [--host H] [--port P] [--out FILE]
                                           [--forward HOST:PORT] [--duration S]
"""

from __future__ import annotations

import argparse
import socket
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from .udp.capture_file import CaptureWriter
from .udp.header import PACKET_NAMES, parse_header, peek_format_and_id

STATUS_INTERVAL = 5.0


def _parse_hostport(text: str) -> tuple[str, int]:
    host, _, port = text.rpartition(":")
    if not host or not port.isdigit():
        raise argparse.ArgumentTypeError("expected HOST:PORT")
    return host, int(port)


def _status_line(elapsed: float, pkts: int, rate: float, counts: Counter,
                 info: dict, gaps: int, frames: int) -> str:
    per_id = " ".join(
        f"{PACKET_NAMES.get(i, i)}={n}" for i, n in sorted(counts.items())
    )
    gap_pct = 100.0 * gaps / (gaps + frames) if (gaps + frames) else 0.0
    return (
        f"[{elapsed:6.1f}s] {pkts} pkts ({rate:.0f}/s) | fmt={info.get('fmt')} "
        f"year={info.get('year')} uid={info.get('uid')} "
        f"frame-gap={gap_pct:.2f}% | {per_id}"
    )


def run_capture(
    out: str | Path,
    host: str = "127.0.0.1",
    port: int = 20777,
    forward: tuple[str, int] | None = None,
    duration: float | None = None,
    stop_event=None,
    ready_event=None,
    bound_port: list | None = None,
    quiet: bool = False,
) -> int:
    """Capture until duration/stop_event/Ctrl+C. Returns packets written.

    ``bound_port`` (a list) receives the actual port, useful with port=0.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    sock.bind((host, port))
    sock.settimeout(0.2)
    if bound_port is not None:
        bound_port.append(sock.getsockname()[1])
    fwd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if forward else None

    counts: Counter = Counter()
    info: dict = {}
    last_frame: int | None = None
    gaps = frames = 0
    total = last_total = 0
    start = last_status = time.monotonic()
    if ready_event is not None:
        ready_event.set()
    if not quiet:
        print(f"Capturing on {host}:{sock.getsockname()[1]} -> {out}"
              + (f" (forwarding to {forward[0]}:{forward[1]})" if forward else ""))
    try:
        with CaptureWriter(out) as writer:
            while True:
                now = time.monotonic()
                if duration is not None and now - start >= duration:
                    break
                if stop_event is not None and stop_event.is_set():
                    break
                try:
                    data, _addr = sock.recvfrom(65535)
                except (socket.timeout, ConnectionResetError):
                    data = None  # timeout keeps Ctrl+C responsive on Windows
                if data is not None:
                    writer.write(time.time(), data)
                    if fwd_sock is not None:
                        try:
                            fwd_sock.sendto(data, forward)
                        except OSError:
                            pass
                    total += 1
                    pk = peek_format_and_id(data)
                    if pk:
                        counts[pk[1]] += 1
                    hdr = parse_header(data)
                    if hdr:
                        info = {"fmt": hdr.packet_format, "year": hdr.game_year,
                                "uid": hdr.session_uid}
                        f = hdr.frame_identifier
                        if last_frame is not None and f > last_frame:
                            if f - last_frame > 1:
                                gaps += f - last_frame - 1
                            frames += 1
                        last_frame = f
                now = time.monotonic()
                if not quiet and now - last_status >= STATUS_INTERVAL:
                    rate = (total - last_total) / (now - last_status)
                    last_status, last_total = now, total
                    print(_status_line(now - start, total, rate, counts, info,
                                       gaps, frames), flush=True)
    except KeyboardInterrupt:
        if not quiet:
            print("\nInterrupted.")
    finally:
        sock.close()
        if fwd_sock is not None:
            fwd_sock.close()
    if not quiet:
        print(f"Done: {total} packets saved to {out}")
    return total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=20777)
    ap.add_argument("--out", default=None)
    ap.add_argument("--forward", type=_parse_hostport, default=None,
                    metavar="HOST:PORT")
    ap.add_argument("--duration", type=float, default=None, metavar="SECONDS")
    args = ap.parse_args(argv)
    out = args.out or str(
        Path("data") / "udp_captures" / f"{datetime.now():%Y%m%d-%H%M%S}.f1cap"
    )
    run_capture(out, args.host, args.port, args.forward, args.duration)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
