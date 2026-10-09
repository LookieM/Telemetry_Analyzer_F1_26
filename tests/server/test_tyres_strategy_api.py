"""Tyres, compound model, strategy optimiser and review endpoints on the Bahrain race."""

from __future__ import annotations

import pytest

TRACK = "Bahrain"


def test_session_tyres(client, race_id):
    body = client.get(f"/api/sessions/{race_id}/tyres").json()
    stints = body["stints"]
    assert [s["stint"]["compound"] for s in stints] == [19, 19, 20]
    assert [s["stint"]["n_laps"] if "n_laps" in s["stint"] else len(s["stint"]["laps"]) for s in stints] == [8, 9, 12]
    first = stints[0]
    for key in ("deg", "wear_rate", "limiting_wheel", "hot_psi", "label", "role", "color", "targets", "pressure"):
        assert key in first, key
    assert {r["Wheel"] for r in first["pressure"]} == {"RL", "RR", "FL", "FR"}
    assert body["wheel_table"] and {"lap", "age", "corr_time"} <= set(body["wheel_table"][0])
    assert set(body["targets"]) == {"19", "20"}
    assert body["allocation"]["19"]["label"] and body["allocation"]["19"]["color"].startswith("#")
    assert body["temp_channel"] and body["race_stats"]["fuel_s_per_kg"] > 0
    assert 30 <= body["wear_limit"] <= 95
    custom = client.get(f"/api/sessions/{race_id}/tyres", params={"wear_limit": 50}).json()
    assert custom["wear_limit"] == 50
    assert client.get("/api/sessions/999999/tyres").status_code == 404


def test_compound_model(client):
    body = client.get(f"/api/tracks/{TRACK}/compound-model", params={"state": "dry"}).json()
    assert body["track"] == TRACK and body["state"] == "dry"
    assert body["compounds"] and all(isinstance(k, str) for k in body["compounds"])
    comp = next(iter(body["compounds"].values()))
    assert {"label", "offset_s", "deg_s_per_lap", "wear_pct_per_lap", "max_laps"} <= set(comp)
    assert body["pit_loss"] is None or body["pit_loss"] > 0
    assert body["stats"]["fuel_s_per_kg"] > 0 and body["sources"]


def test_optimise(client, race_id):
    body = client.post("/api/strategy/optimise", json={"track": TRACK, "state": "dry"}).json()
    plans, params = body["plans"], body["params"]
    assert plans and plans[0]["race_time"] == min(p["race_time"] for p in plans)
    assert len(plans) <= 8
    for p in plans:
        assert sum(p["stints"]) == params["laps"]
        assert len(p["windows"]) == p["stops"] == len(p["stop_laps"])
        for lap, (lo, hi) in zip(p["stop_laps"], p["windows"]):
            assert lo <= lap <= hi
    assert body["best"] == plans[0]
    assert params["start_fuel_kg"] == pytest.approx((params["laps"] + params["fuel_margin_laps"]) * params["fuel_per_lap_kg"])
    assert body["sensitivity"] and body["calls"] and body["sources"]
    trace = body["race_trace"]
    assert 1 <= len(trace["plans"]) <= 4 and len(trace["laps"]) == params["laps"]
    assert all(len(p["lap_times"]) == params["laps"] for p in trace["plans"])
    assert body["specs"] and {"code", "offset_s", "deg_s_per_lap"} <= set(body["specs"][0])


def test_optimise_overrides_and_bad_body(client):
    base = client.post("/api/strategy/optimise", json={"track": TRACK}).json()
    laps = base["params"]["laps"]
    code = base["specs"][0]["code"]
    over = client.post(
        "/api/strategy/optimise",
        json={"track": TRACK, "params": {"laps": laps - 4, "max_stops": 1}, "specs": [{"code": code, "use": False}]},
    ).json()
    assert over["params"]["laps"] == laps - 4
    assert all(p["stops"] <= 1 and code not in p["compounds"] for p in over["plans"])
    assert client.post("/api/strategy/optimise", json={}).status_code == 422
    assert client.post("/api/strategy/optimise", json={"track": TRACK, "params": {"laps": "x"}}).status_code == 422
    assert client.post("/api/strategy/optimise", json={"track": TRACK, "params": {"nope": 1}}).status_code == 422
    assert client.post("/api/strategy/optimise", json={"track": TRACK, "specs": [{"code": 99}]}).status_code == 422


def test_strategy_review(client, race_id):
    body = client.get(f"/api/sessions/{race_id}/strategy-review").json()
    assert body["is_race"] and body["reason"] is None
    review = body["review"]
    assert tuple(review["actual"]["compounds"]) == (19, 19, 20)
    assert tuple(review["actual"]["stints"]) == (8, 9, 12)
    assert review["strategy_cost_s"] >= 0 and review["best"]["race_time"] > 0
    assert len(review["actual_lap_times"]) == body["params"]["laps"]
    assert isinstance(body["game_pit_windows"], list)


def test_review_unavailable_reason(lib_root, race_id):
    from telemetry import strategy, tyres

    _, _, summary = tyres.session_frames(race_id, lib_root)
    params = strategy.RaceParams(laps=10, pit_loss_s=20.0)
    spec = strategy.CompoundSpec(19, "C2", "#fff", 0.0, 0.1, 3.0)
    assert "race laps are set to 10 but this race ran 29" in strategy.review_unavailable_reason(summary, {19: spec, 20: spec}, params, "dry")
    assert "does not include" in strategy.review_unavailable_reason(summary, {19: spec}, params, "dry")


def test_strategy_review_404(client):
    assert client.get("/api/sessions/999999/strategy-review").status_code == 404
