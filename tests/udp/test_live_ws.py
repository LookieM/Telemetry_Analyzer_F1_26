import socket
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from telemetria_server.app import create_app
from telemetria_server.config import Config
from telemetria_server.udp.capture_file import iter_capture

CAP = Path(__file__).resolve().parents[2] / "data" / "udp_captures" / "20261009-222554.f1cap"
pytestmark = pytest.mark.skipif(not CAP.exists(), reason="no local capture")


def test_replay_over_udp_reaches_websocket(tmp_path):
    cfg = Config(record=True, udp_port=0, live_rate_hz=20, app_root=tmp_path)
    app = create_app(cfg, frontend_dist=tmp_path / "none")
    with TestClient(app) as client:
        ing = app.state.ingest
        port = ing.transport.get_extra_info("sockname")[1]
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        with client.websocket_connect("/ws/live") as ws:
            assert ws.receive_json()["type"] == "status"
            for i, (_t, d) in enumerate(iter_capture(CAP)):
                if i < 200_000:
                    continue
                tx.sendto(d, ("127.0.0.1", port))
                if i % 300 == 0:
                    time.sleep(0.005)
                if i > 203_000:
                    break
            snap, kinds = None, set()
            deadline = time.time() + 20
            while time.time() < deadline and snap is None:
                m = ws.receive_json()
                kinds.add(m["type"])
                if m["type"] == "snapshot":
                    snap = m
        tx.close()
        assert snap is not None
        assert snap["session"]["track"] == "Spa" and snap["session"]["total_laps"] == 11
        assert set(snap["tyres"]["wheels"]) == {"FL", "FR", "RL", "RR"}
        assert 0 < snap["fuel"]["kg"] < 110 and snap["timing"]["lap_time"] >= 0
        assert any(r["you"] for r in snap["rivals"])
        st = client.get("/api/live/status").json()
        assert st["enabled"] and st["packets"] > 500
