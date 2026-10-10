import asyncio
import socket
from pathlib import Path

import pytest

from telemetria_server.config import Config
from telemetria_server.ingest import SessionManager, UdpIngest
from telemetria_server.udp.capture_file import iter_capture

CAP = Path(__file__).resolve().parents[2] / "data" / "udp_captures" / "20261009-222554.f1cap"
pytestmark = pytest.mark.skipif(not CAP.exists(), reason="no local capture")


def test_manager_ends_session_on_idle_and_uid_change():
    done = []
    mgr = SessionManager(done.append, idle_s=60)
    last = 0.0
    for i, (t, d) in enumerate(iter_capture(CAP)):
        if i > 40_000:
            break
        mgr.feed(d, t)
        last = t
    assert not done
    mgr.tick(last + 30)
    assert not done
    mgr.tick(last + 61)
    assert len(done) == 1 and done[0].has_data and done[0].track_id == 10
    assert mgr.rec.session_uid is None  # fresh recorder


def test_udp_socket_roundtrip(tmp_path):
    async def run():
        ing = UdpIngest(Config(record=True, udp_port=0, host="127.0.0.1", app_root=tmp_path))
        assert await ing.start()
        port = ing.transport.get_extra_info("sockname")[1]
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for i, (_t, d) in enumerate(iter_capture(CAP)):
            if i > 3000:
                break
            tx.sendto(d, ("127.0.0.1", port))
            if i % 200 == 0:
                await asyncio.sleep(0.01)
        await asyncio.sleep(0.3)
        n = ing.mgr.packets
        await ing.stop()
        tx.close()
        return n

    assert asyncio.run(run()) > 1500
