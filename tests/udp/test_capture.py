"""Tests for raw UDP capture, forwarding and capture summaries."""

import socket
import struct
import threading
import time

from telemetria_server.capture import run_capture
from telemetria_server.capture_info import summarize
from telemetria_server.udp.capture_file import MAGIC, iter_capture
from telemetria_server.udp.header import parse_header


def make_packet(pid: int, frame: int, size: int, uid: int = 42) -> bytes:
    head = struct.pack("<HBBBBBQfIIBB", 2025, 25, 1, 0, 1, pid, uid,
                       frame / 60.0, frame, frame, 0, 255)
    return head + bytes(size - len(head))


def _send_all(packets, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for p in packets:
        s.sendto(p, ("127.0.0.1", port))
        time.sleep(0.002)
    s.close()


def test_capture_roundtrip_forward_and_summary(tmp_path):
    out = tmp_path / "c.f1cap"
    fwd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fwd.bind(("127.0.0.1", 0))
    fwd.settimeout(2)
    fwd_port = fwd.getsockname()[1]

    ready, bound = threading.Event(), []
    th = threading.Thread(target=run_capture, kwargs=dict(
        out=out, port=0, forward=("127.0.0.1", fwd_port), duration=1.5,
        ready_event=ready, bound_port=bound, quiet=True))
    th.start()
    assert ready.wait(2)

    packets = [make_packet(6, f, 60) for f in range(10)]
    packets += [make_packet(2, f, 80) for f in (0, 1, 4)]  # gap of 2
    _send_all(packets, bound[0])
    got = [fwd.recvfrom(65535)[0] for _ in packets]
    th.join(5)
    fwd.close()

    assert got == packets
    recs = list(iter_capture(out))
    assert [p for _, p in recs] == packets
    hdr = parse_header(recs[0][1])
    assert hdr and hdr.packet_format == 2025 and hdr.packet_id == 6

    s = summarize(out)
    assert s["packets"] == 13
    assert s["by_id"][6]["count"] == 10 and s["by_id"][6]["sizes"] == [60]
    assert s["by_id"][2]["count"] == 3 and s["by_id"][2]["gaps"] == 2
    assert s["session_uids"] == [42]


def test_truncated_file_tolerated(tmp_path):
    out = tmp_path / "t.f1cap"
    pkt = make_packet(0, 1, 50)
    rec = struct.pack("<Id", len(pkt), 1.0) + pkt
    out.write_bytes(MAGIC + rec + rec[:-10])
    assert [p for _, p in iter_capture(out)] == [pkt]
    assert summarize(out)["packets"] == 1
