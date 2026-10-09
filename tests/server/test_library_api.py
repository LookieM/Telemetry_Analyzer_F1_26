"""REST tests for the library endpoints, run against a temporary copy of the library."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from conftest import ROOT
from telemetria_server.app import create_app
from telemetria_server.config import Config, load_config
from telemetria_server.serialization import to_jsonable


def test_health(empty_client):
    assert empty_client.get("/api/health").json() == {"status": "ok"}


def test_empty_library(empty_client):
    stats = empty_client.get("/api/library/stats").json()
    assert stats["sessions"] == 0
    assert empty_client.get("/api/sessions").json() == []
    assert empty_client.get("/api/sessions/1").status_code == 404
    assert empty_client.patch("/api/sessions/1", json={"notes": "x"}).status_code == 404
    assert empty_client.delete("/api/sessions/1").status_code == 404


def test_stats_and_list(client, race_id):
    stats = client.get("/api/library/stats").json()
    assert stats["sessions"] >= 1 and stats["stored_bytes"] > 0

    rows = client.get("/api/sessions").json()
    race = next(r for r in rows if r["id"] == race_id)
    assert race["source_name"] == "bahrain_race.csv"
    assert "setup_json" not in race
    assert race["lap_count"] > 10

    by_track = client.get("/api/sessions", params={"track": race["track"].lower()}).json()
    assert race_id in {r["id"] for r in by_track}
    assert all(r["track"] == race["track"] for r in by_track)
    client.patch(f"/api/sessions/{race_id}", json={"session_type": "Race"})
    by_type = client.get("/api/sessions", params={"type": "Race"}).json()
    assert race_id in {r["id"] for r in by_type} and all(r["session_type"] == "Race" for r in by_type)
    assert client.get("/api/sessions", params={"track": "Nowhere"}).json() == []


def test_session_detail(client, race_id):
    body = client.get(f"/api/sessions/{race_id}").json()
    assert body["session"]["id"] == race_id and "setup_json" not in body["session"]
    laps = pd.DataFrame(body["laps"]).set_index("lap")
    for col in ("lap_class", "pit_stop", "fresh_set", "tyre_age", "compound_label", "lap_time"):
        assert col in laps.columns
    assert [int(lap) for lap in laps.index[laps["pit_stop"]]] == [8, 17]
    assert laps["fresh_set"].dtype == bool
    assert laps["compound_label"].map(lambda v: isinstance(v, str)).all()
    assert client.get("/api/sessions/999999").status_code == 404


def test_patch_session(client, race_id):
    r = client.patch(f"/api/sessions/{race_id}", json={"notes": "hello", "conditions": " Dry "})
    assert r.status_code == 200
    assert r.json()["notes"] == "hello" and r.json()["conditions"] == "Dry"
    assert client.get("/api/sessions").json()[0].keys()  # list still works
    row = next(x for x in client.get("/api/sessions").json() if x["id"] == race_id)
    assert row["notes"] == "hello"


def test_delete_session(client, race_id, lib_root: Path):
    tel = next((lib_root / "data" / "sessions").glob("*.parquet"))
    assert client.delete(f"/api/sessions/{race_id}").json() == {"deleted": race_id}
    assert client.get(f"/api/sessions/{race_id}").status_code == 404
    assert not tel.exists()


def test_warm_latency(client, race_id):
    client.get("/api/sessions")
    client.get(f"/api/sessions/{race_id}")
    t0 = time.perf_counter()
    client.get("/api/sessions")
    t1 = time.perf_counter()
    client.get(f"/api/sessions/{race_id}")
    t2 = time.perf_counter()
    print(f"\nlist {1000 * (t1 - t0):.1f} ms, detail {1000 * (t2 - t1):.1f} ms")
    assert t2 - t1 < 1.0


def test_token_middleware(tmp_path):
    app = create_app(Config(app_root=tmp_path, access_token="s3cret"), frontend_dist=tmp_path / "none")
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 401
        assert c.get("/api/health", params={"token": "bad"}).status_code == 401
        ok = c.get("/api/health", params={"token": "s3cret"})
        assert ok.status_code == 200 and "telemetria_token" in ok.headers["set-cookie"]
        assert c.get("/api/health").status_code == 200  # cookie now stored by the client
    with TestClient(app, cookies={"telemetria_token": "s3cret"}) as c:
        assert c.get("/api/health").status_code == 200


def test_open_by_default(empty_client):
    assert empty_client.get("/api/health").status_code == 200


def test_static_mount_only_with_dist(tmp_path):
    with TestClient(create_app(Config(app_root=tmp_path), frontend_dist=tmp_path / "missing")) as c:
        assert c.get("/").status_code == 404
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>hi</html>", encoding="utf-8")
    with TestClient(create_app(Config(app_root=tmp_path), frontend_dist=dist)) as c:
        assert "hi" in c.get("/").text
        assert c.get("/api/health").status_code == 200  # API routes win over the static mount


def test_serialization():
    out = to_jsonable(
        {
            "a": np.float32(1.5),
            "n": np.int64(3),
            "nan": float("nan"),
            "inf": np.inf,
            "arr": np.array([1.0, np.nan]),
            "df": pd.DataFrame({"x": [1, 2], "y": [np.nan, 0.5]}),
            "s": pd.Series([1, 2]),
            "p": Path("a/b"),
            "b": np.bool_(True),
        }
    )
    assert out == {
        "a": 1.5, "n": 3, "nan": None, "inf": None, "arr": [1.0, None],
        "df": [{"x": 1, "y": None}, {"x": 2, "y": 0.5}], "s": [1, 2], "p": str(Path("a/b")), "b": True,
    }


def test_load_config(tmp_path):
    assert load_config(tmp_path / "missing.toml").port == 8765
    f = tmp_path / "t.toml"
    f.write_text('port = 9000\naccess_token = "x"\nunknown = 1\n', encoding="utf-8")
    cfg = load_config(f)
    assert (cfg.port, cfg.access_token, cfg.host) == (9000, "x", "127.0.0.1")


def test_backend_does_not_import_streamlit():
    code = (
        "import sys, telemetria_server.app, telemetria_server.api.library;"
        "sys.exit(1 if 'streamlit' in sys.modules else 0)"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
