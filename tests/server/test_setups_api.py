"""Setups page API (list, naming, offline duel) on a tmp copy of the library's Hungaroring sessions."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import DB_PATH, ROOT, copy_library_db
from telemetria_server.app import create_app
from telemetria_server.config import Config

TRACK = "Hungaroring"
C4_A = "c6c01d823cac7de4"  # 10 clean laps on C4
C4_B = "e09da847b39c11fc"  # 8 clean laps on C4 (+ C5 runs)
INTERS = "4555cb24f549010b"  # inter / wet runs only


@pytest.fixture(scope="module")
def hun_root(tmp_path_factory) -> Path:
    if not DB_PATH.exists():
        pytest.skip("personal telemetry library (data/) not present")
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    paths = [r[0] for r in con.execute("SELECT telemetry_path FROM sessions WHERE track LIKE 'Hungar%'")]
    con.close()
    if not paths:
        pytest.skip("no Hungaroring sessions in this library")
    root = tmp_path_factory.mktemp("hun")
    (root / "data" / "sessions").mkdir(parents=True)
    copy_library_db(root / "data" / "telemetry.db")
    for p in paths:
        shutil.copy2(ROOT / p, root / "data" / "sessions" / Path(p).name)
    return root


@pytest.fixture
def hun(hun_root):
    with TestClient(create_app(Config(record=False, app_root=hun_root), frontend_dist=hun_root / "no_dist")) as c:
        yield c


def _setups(client) -> dict:
    body = client.get(f"/api/tracks/{TRACK}/setups").json()
    return {s["fingerprint"]: s for s in body["setups"]}


def test_setups_list_groups_runs_by_fingerprint(hun):
    setups = _setups(hun)
    if C4_A not in setups:
        pytest.skip("library differs from the one this test was written against")
    s = setups[C4_A]
    assert s["name"] is None and s["n_runs"] == len(s["runs"]) >= 1 and s["n_clean"] >= 3
    run = max(s["runs"], key=lambda r: r["n_clean"])
    for key in ("session_id", "session_type", "run", "first_lap", "last_lap", "n_laps", "n_clean", "compound_label", "state", "fuel_kg", "pace_s", "best_s", "wear_pct_per_lap"):
        assert key in run
    assert run["compound_label"] == "C4" and run["best_s"] <= run["pace_s"]


def test_duel_ranks_comparable_setups_and_stores_it(hun, hun_root):
    if C4_A not in _setups(hun):
        pytest.skip("library differs from the one this test was written against")
    r = hun.post(f"/api/tracks/{TRACK}/duel", json={"fingerprints": [C4_A, C4_B]}).json()
    assert r["comparable"] and r["reasons"] == []
    assert r["condition"]["compound_label"] == "C4" and r["condition"]["state"] == "dry"
    rk = r["ranking"]
    assert set(rk["order"]) == {C4_A, C4_B} and rk["winner"] == rk["order"][0]
    assert rk["tie_break"] in ("stopwatch", "balance", "none") and rk["noise_s"] >= 0.10
    assert rk["weights"] == {"race": 0.7, "quali": 0.3} and rk["cost_source"] in ("model", "fallback")
    assert rk["same_session"] is False and rk["noise_s"] >= 0.5
    assert any(c.startswith("Laps come from different sessions (#") for c in rk["callouts"])
    assert all(c["sessions"] for c in rk["contestants"])
    for c in rk["contestants"]:
        assert c["n_laps"] >= 3 and c["score_s"] > 60
        assert c["score_s"] == pytest.approx(0.7 * (c["race_pace_s"] + c["race_cost_s"]) + 0.3 * c["quali_pace_s"])
        assert set(c["balance"]) >= {"entry", "mid", "exit", "distance"}
    from telemetry.duel_store import get_duel

    stored = get_duel(r["duel_id"], hun_root)
    assert stored["mode"] == "offline" and stored["track"] == TRACK and stored["result"]["ranking"]["winner"] == rk["winner"]


def test_duel_reports_why_setups_are_not_comparable(hun):
    if INTERS not in _setups(hun) or C4_A not in _setups(hun):
        pytest.skip("library differs from the one this test was written against")
    r = hun.post(f"/api/tracks/{TRACK}/duel", json={"fingerprints": [C4_A, INTERS]}).json()
    assert r["comparable"] is False and r["ranking"] is None
    assert r["reasons"] and ("compound" in r["reasons"][0])
    assert r["pairs"][0]["comparable"] is False


def test_naming_a_setup_shows_in_the_list_and_the_duel(hun):
    if C4_A not in _setups(hun):
        pytest.skip("library differs from the one this test was written against")
    put = hun.put(f"/api/setups/{C4_A}/name", json={"track": TRACK, "name": "  Internet A "})
    assert put.json()["name"] == "Internet A"
    assert _setups(hun)[C4_A]["name"] == "Internet A"
    r = hun.post(f"/api/tracks/{TRACK}/duel", json={"fingerprints": [C4_A, C4_B]}).json()
    assert r["names"][C4_A] == "Internet A" and r["names"][C4_B].startswith("Setup ")
    assert hun.put(f"/api/setups/{C4_A}/name", json={"track": TRACK, "name": ""}).json()["name"] is None
    assert _setups(hun)[C4_A]["name"] is None


def test_duel_input_errors(hun):
    assert hun.post(f"/api/tracks/{TRACK}/duel", json={"fingerprints": [C4_A]}).status_code == 422
    assert hun.post(f"/api/tracks/{TRACK}/duel", json={"fingerprints": [C4_A, C4_A]}).status_code == 422
    assert hun.post(f"/api/tracks/{TRACK}/duel", json={"fingerprints": ["a", "b", "c", "d"]}).status_code == 422
    assert hun.post(f"/api/tracks/{TRACK}/duel", json={"fingerprints": [C4_A, "nope"]}).status_code == 404


def test_empty_library_has_no_setups(empty_client):
    assert empty_client.get("/api/tracks/Monza/setups").json() == {"track": "Monza", "setups": []}
    assert empty_client.put("/api/setups/abc/name", json={"track": "Monza", "name": "x"}).json()["name"] == "x"
    assert empty_client.get("/api/tracks/Monza/setups").json()["setups"] == []
