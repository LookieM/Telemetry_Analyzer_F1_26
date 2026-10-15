"""Live duel over HTTP: routes, 409 rules (one program at a time), snapshot key, persistence + baseline."""

import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from telemetria_server import duel_library
from telemetria_server.app import create_app
from telemetria_server.config import Config
from telemetria_server.live.engineer import EngineerLap
from telemetria_server.live.state import PID_LAP, PID_SESSION
from telemetria_server.udp.capture_file import iter_capture
from telemetry import duel_store

CAP = Path(__file__).resolve().parents[2] / "data" / "udp_captures" / "20261009-222554.f1cap"
D = "/api/live/duel/"
E = "/api/live/engineer/"
BASE = {"wing_setup_0": 25.0, "wing_setup_1": 20.0, "diff_onThrottle_setup": 1.0, "brake_bias_setup": 0.56}


def client(tmp_path, **kw):
    cfg = Config(record=True, udp_port=0, live_rate_hz=20, app_root=tmp_path, **kw)
    return TestClient(create_app(cfg, frontend_dist=tmp_path / "none"))


def test_without_live_data_and_disabled_ingest(tmp_path):
    with client(tmp_path) as c:
        r = c.post(D + "start", json={"n": 2})
        assert r.status_code == 409 and "No live session" in r.json()["detail"]
        assert c.post(D + "stop").status_code == 409 and c.post(D + "skip").status_code == 409
        assert c.post(D + "rank", json={"order": ["A", "B"]}).status_code == 409
        assert c.post(D + "confirm", json={"winner": "A"}).status_code == 409
        assert c.post(D + "start", json={"n": 4}).status_code == 422
        assert c.get("/api/live/status").json()["snapshot"] is None
    with TestClient(create_app(Config(record=False, app_root=tmp_path), frontend_dist=tmp_path / "none")) as c:
        assert c.post(D + "start", json={"n": 2}).status_code == 503


def test_access_token_rule(tmp_path):
    with client(tmp_path, access_token="tok") as c:
        assert c.post(D + "stop").status_code == 401
        assert c.post(D + "stop?token=tok").status_code == 409


def _practice(c):
    ing = c.app.state.ingest
    for i, (t, d) in enumerate(iter_capture(CAP)):
        ing.live.feed(d, t)
        if i > 3000:
            break
    deadline = time.time() + 5
    while ing.live.new_session and time.time() < deadline:
        time.sleep(0.05)
    s = ing.live
    sess = np.array([s.pk[PID_SESSION]])
    sess[0]["m_sessionType"], sess[0]["m_weather"] = 1, 0
    s.pk[PID_SESSION] = sess[0]
    lap = np.array([s.pk[PID_LAP]])
    lap[0]["m_lapData"][s.player]["m_driverStatus"] = 0
    s.pk[PID_LAP] = lap[0]
    return ing


def _laps(eng, setup, times, start):
    for i, t in enumerate(times):
        with eng._eng_lock:
            eng.duel.on_lap(EngineerLap(lap=start + i, lap_time_s=t, setup=dict(setup), compound=18, tyre_set_idx=1,
                                        tyre_age_laps=2 + i))
    return start + len(times)


@pytest.mark.skipif(not CAP.exists(), reason="no local capture")
def test_duel_start_rank_confirm_stores_duel_and_baseline(tmp_path):
    with client(tmp_path) as c:
        ing = _practice(c)
        eng = ing.engine
        r = c.post(D + "start", json={"n": 2, "names": ["Internet A", ""]})
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["phase"] == "running" and v["contestants"][0]["label"] == "Internet A"
        assert c.post(D + "start", json={"n": 2}).status_code == 409                    # already running
        assert c.post(E + "start", json={"program": "short"}).status_code == 409        # one program at a time
        snap = c.get("/api/live/status").json()["snapshot"]
        assert snap["duel"]["phase"] == "running" and snap["engineer"] is None

        n = _laps(eng, BASE, [90.0, 90.1, 89.9, 90.0], 1)
        _laps(eng, {**BASE, "wing_setup_0": 30.0}, [91.0, 91.1, 90.9, 91.0], n)
        with eng._eng_lock:
            eng.duel.on_garage(True, 5000.0)
        assert c.post(D + "rank", json={"order": ["A"]}).status_code == 422
        assert c.post(D + "rank", json={"order": ["A", "A"]}).status_code == 409
        r = c.post(D + "rank", json={"order": ["B", "A"], "note": "B felt better"})
        assert r.status_code == 200, r.text
        assert r.json()["phase"] == "review" and r.json()["ranking"]["winner"] == "A"
        assert c.post(D + "confirm", json={"winner": "AB"}).status_code == 422
        r = c.post(D + "confirm", json={"winner": "A"})
        assert r.status_code == 200 and r.json()["phase"] == "done" and r.json()["winner"] == "A"

        track = duel_library.track_name(c.get("/api/live/status").json()["snapshot"]["session"]["track"])
        deadline = time.time() + 5
        while time.time() < deadline and duel_store.get_baselines(track, tmp_path)["active"] is None:
            time.sleep(0.05)
        base = duel_store.get_baselines(track, tmp_path)["active"]
        assert base and base["source"] == "duel" and base["name"] == "Internet A"
        assert base["setup"]["wing_setup_0"] == 25.0 and base["ref_id"]
        duel = duel_store.get_duel(base["ref_id"], tmp_path)
        assert duel["mode"] == "live" and duel["result"]["winner"] == "A"
        assert any(e["kind"] == "engineer" for e in ing.recent_events if e.get("type") == "event")

        # the engineer can start again once the duel finished
        assert c.post(E + "start", json={"program": "short"}).status_code == 200
        assert c.post(D + "start", json={"n": 2}).status_code == 409                    # engineer running
        c.post(E + "stop")


@pytest.mark.skipif(not CAP.exists(), reason="no local capture")
def test_stop_keeps_the_duel_without_a_baseline_and_refuses_races(tmp_path):
    with client(tmp_path) as c:
        ing = _practice(c)
        eng = ing.engine
        assert c.post(D + "start", json={"n": 2}).status_code == 200
        n = _laps(eng, BASE, [90.0, 90.1, 89.9, 90.0], 1)
        _laps(eng, {**BASE, "wing_setup_0": 30.0}, [91.0, 91.1, 90.9, 91.0], n)
        r = c.post(D + "stop")
        assert r.status_code == 200 and r.json()["phase"] == "done" and r.json()["winner"] is None
        track = duel_library.track_name(c.get("/api/live/status").json()["snapshot"]["session"]["track"])
        deadline = time.time() + 5
        rows = []
        with duel_store.connect(tmp_path) as conn:
            while time.time() < deadline and not rows:
                time.sleep(0.05)
                rows = conn.execute("SELECT id FROM duels WHERE mode = 'live'").fetchall() if _has_table(conn) else []
        assert rows
        assert duel_store.get_baselines(track, tmp_path)["active"] is None

        # race: refused
        s = ing.live
        sess = np.array([s.pk[PID_SESSION]])
        sess[0]["m_sessionType"] = 15
        s.pk[PID_SESSION] = sess[0]
        r = c.post(D + "start", json={"n": 2})
        assert r.status_code == 409 and "practice" in r.json()["detail"]


def _has_table(conn) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'duels'").fetchone())
