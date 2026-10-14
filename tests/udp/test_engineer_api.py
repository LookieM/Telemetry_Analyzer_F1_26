import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from telemetria_server.app import create_app
from telemetria_server.config import Config
from telemetria_server.live.engineer import EngineerLap
from telemetria_server.live.state import PID_LAP, PID_SESSION
from telemetria_server.udp.capture_file import iter_capture
from telemetry import engineer_log

CAP = Path(__file__).resolve().parents[2] / "data" / "udp_captures" / "20261009-222554.f1cap"
P = "/api/live/engineer/"


def client(tmp_path, **kw):
    cfg = Config(record=True, udp_port=0, live_rate_hz=20, app_root=tmp_path, **kw)
    return TestClient(create_app(cfg, frontend_dist=tmp_path / "none"))


def test_start_without_live_data_is_409(tmp_path):
    with client(tmp_path) as c:
        r = c.post(P + "start", json={"program": "short"})
        assert r.status_code == 409 and "No live session" in r.json()["detail"]
        assert c.post(P + "stop").status_code == 409 and c.post(P + "skip").status_code == 409
        assert c.post(P + "start", json={"program": "huge"}).status_code == 422
        assert c.get("/api/live/status").json()["snapshot"] is None


def test_503_when_live_ingest_is_disabled(tmp_path):
    cfg = Config(record=False, app_root=tmp_path)
    with TestClient(create_app(cfg, frontend_dist=tmp_path / "none")) as c:
        assert c.post(P + "start", json={"program": "short"}).status_code == 503
        assert c.post(P + "stop").status_code == 503


def test_access_token_rule_matches_the_live_socket(tmp_path):
    with client(tmp_path, access_token="tok") as c:
        assert c.post(P + "stop").status_code == 401
        assert c.post(P + "stop?token=wrong").status_code == 401
        assert c.post(P + "stop?token=tok").status_code == 409       # through the gate, nothing running
        assert c.post(P + "stop").status_code == 409                  # the gate set the cookie


@pytest.mark.skipif(not CAP.exists(), reason="no local capture")
def test_start_answer_confirm_stop_over_a_fake_practice_state(tmp_path):
    with client(tmp_path) as c:
        ing = c.app.state.ingest
        for i, (t, d) in enumerate(iter_capture(CAP)):
            ing.live.feed(d, t)
            if i > 3000:
                break
        deadline = time.time() + 5
        while ing.live.new_session and time.time() < deadline:
            time.sleep(0.05)                                           # let the loop reset for the new session
        s = ing.live
        sess = np.array([s.pk[PID_SESSION]])
        sess[0]["m_sessionType"], sess[0]["m_weather"] = 1, 0           # FP1, clear
        s.pk[PID_SESSION] = sess[0]
        lap = np.array([s.pk[PID_LAP]])
        lap[0]["m_lapData"][s.player]["m_driverStatus"] = 0              # in the garage
        s.pk[PID_LAP] = lap[0]

        r = c.post(P + "start", json={"program": "short", "minutes": 20})
        assert r.status_code == 200, r.text
        view = r.json()
        assert view["phase"] == "balance" and view["param"]["label"] == "Front wing"
        assert c.post(P + "start", json={"program": "short"}).status_code == 409   # already running
        assert c.get("/api/live/status").json()["snapshot"]["engineer"]["phase"] == "balance"

        eng, n = ing.engine, 0
        for v, value in view["variants"].items():
            for k in range(3):
                n += 1
                with eng._eng_lock:
                    eng.engineer.on_lap(EngineerLap(lap=n, lap_time_s=90.0 + (0.5 if v == "2" else 0.0),
                                                    setup={"wing_setup_0": float(value)}, compound=18))
        deadline = time.time() + 5
        while time.time() < deadline:
            q = c.get("/api/live/status").json()["snapshot"]["engineer"]["question"]
            if q["pending"]:
                break
            time.sleep(0.05)
        assert q["pending"]
        bad = c.post(P + "answer", json={"verdict": "1", "tags": ["nope"]})
        assert bad.status_code == 409
        r = c.post(P + "answer", json={"verdict": "1", "strength": "clear", "tags": ["traction"], "note": "x"})
        assert r.status_code == 200 and r.json()["last_result"]["stopwatch_winner"] == "1"
        assert c.post(P + "confirm", json={"winner": "1"}).status_code == 200
        r = c.post(P + "stop")
        assert r.status_code == 200 and r.json()["phase"] == "done"

        deadline = time.time() + 5
        while time.time() < deadline and not engineer_log.list_tests("Spa", tmp_path):
            time.sleep(0.05)
        tests = engineer_log.list_tests("Spa", tmp_path)
        assert len(tests) == 1 and tests[0]["program"] == "short" and tests[0]["result"]["pairs"]
        assert any(e["kind"] == "engineer" for e in ing.recent_events if e.get("type") == "event")
