"""Generated setup API on an empty tmp library (catalogue profiles) with synthetic baselines as evidence."""

from __future__ import annotations

import pytest

from telemetry import engineer_log
from telemetry.db import connect
from telemetry.setup_generator import SOURCE_WEIGHTS, prior_for
from telemetry.setup_tweaker import psi_to_pa

SPIELBERG = {
    "wing_setup_0": 36, "wing_setup_1": 30, "diff_onThrottle_setup": 0.7, "arb_setup_0": 9, "arb_setup_1": 11,
    "susp_spring_setup_0": 36, "susp_spring_setup_1": 20, "brake_bias_setup": 0.58,
    "susp_height_setup_0": 20, "susp_height_setup_1": 20, "tyre_press_setup_0": psi_to_pa(25.0), "tyre_press_setup_1": psi_to_pa(25.0),
}


def _gen(client, track="Suzuka"):
    r = client.get(f"/api/tracks/{track}/generated-setup")
    assert r.status_code == 200, r.text
    return r.json()


def test_catalogue_only_track_is_prior_only_and_low(empty_client):
    g = _gen(empty_client)
    assert g["track"] == "Suzuka" and g["profile"]["source"] == "catalogue"
    assert g["overall_confidence"] == "low" and g["group_confidence"] == {"aero": "low", "mechanical": "low"}
    fw = g["setup"]["wing_setup_0"]
    assert fw["source"] == "prior" and fw["confidence"] == "low" and fw["evidence"] == [] and fw["display"] == 24  # Suzuka preset FW 24
    assert g["first_test"]["key"] == "wing_setup_0" and "prior only" in g["first_test"]["text"]
    assert g["fuel"]["quali_kg"] == 5 and 5 <= g["fuel"]["race_kg"] <= 110 and g["fuel"]["source"] == "default kg/km"
    assert g["setup"]["fuel_setup"]["value"] == g["fuel"]["race_kg"]
    for key in ("camber_setup_0", "camber_setup_1"):
        assert g["setup"][key]["source"] == "meta"
    keys = [d["key"] for d in g["display"]]
    assert keys[0] == "fuel_setup" and "front_brake_bias" not in keys
    assert {d["group"] for d in g["display"]} >= {"Fuel", "Aero", "Transmission", "Geometry", "Suspension", "Brakes", "Tyres"}
    assert all(d["confidence"] in ("low", "medium", "high") for d in g["display"])


def test_every_catalogue_layout_generates(empty_client):
    tracks = empty_client.get("/api/tracks").json()["tracks"]
    assert len(tracks) == 28
    for t in tracks:
        r = empty_client.get(f"/api/tracks/{t['track']}/generated-setup")
        assert r.status_code == 200, t["track"]


def test_unknown_track_404(empty_client):
    assert empty_client.get("/api/tracks/Nowhere/generated-setup").status_code == 404
    assert empty_client.get("/api/tracks/Nowhere/profile").status_code == 404


def test_profile_endpoint(empty_client):
    p = empty_client.get("/api/tracks/Monza/profile").json()
    assert p["source"] == "catalogue" and 0 < p["full_throttle_frac"] < 1


def test_baseline_on_another_track_becomes_evidence(empty_client):
    assert empty_client.post("/api/tracks/Spielberg/baseline", json={"setup": SPIELBERG, "source": "manual"}).status_code == 200
    g = _gen(empty_client)
    fw = g["setup"]["wing_setup_0"]
    assert fw["source"] == "blend" and fw["evidence"][0]["track"] == "Spielberg" and fw["evidence"][0]["source"] == "baseline"
    ev0 = fw["evidence"][0]
    spiel = prior_for("Spielberg")[0]["wing_setup_0"]
    suz = prior_for("Suzuka")[0]["wing_setup_0"]
    assert ev0["found"] == 36 and 0 < ev0["similarity"] <= 1
    assert ev0["offset"] == pytest.approx(36 - spiel) and ev0["value"] == pytest.approx(suz + 36 - spiel)  # an offset, not 36
    assert min(suz, ev0["value"]) - 1 <= fw["value"] <= max(suz, ev0["value"]) + 1
    assert g["setup"]["arb_setup_0"]["evidence"] and g["evidence_tracks"] == ["Spielberg"]
    assert g["setup"]["wing_setup_0"]["weight"] == pytest.approx(fw["evidence"][0]["similarity"] * SOURCE_WEIGHTS["baseline"])


def test_reverse_layout_uses_forward_layout_evidence(empty_client):
    empty_client.post("/api/tracks/Spielberg/baseline", json={"setup": SPIELBERG, "source": "manual"})
    g = _gen(empty_client, "Spielberg Reverse")
    fw = g["setup"]["wing_setup_0"]
    assert fw["evidence"][0]["track"] == "Spielberg" and fw["evidence"][0]["similarity"] > 0.5


def test_settled_values_are_evidence(empty_client, tmp_path):
    engineer_log.ensure_engineer_schema(tmp_path)
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO engineer_settled (track, param, value, updated_at) VALUES ('Spielberg', 'arb_setup_0', 5, '2026-10-01T00:00:00+00:00')")
    arb = _gen(empty_client)["setup"]["arb_setup_0"]
    assert arb["evidence"][0]["source"] == "settled" and arb["evidence"][0]["found"] == 5 and arb["evidence"][0]["offset"] is not None


def test_own_baseline_is_not_evidence_for_itself_but_generator_still_runs(empty_client):
    empty_client.post("/api/tracks/Suzuka/baseline", json={"setup": SPIELBERG, "source": "manual"})
    g = _gen(empty_client)
    assert g["setup"]["wing_setup_0"]["source"] == "prior" and g["evidence_tracks"] == []
    assert empty_client.get("/api/tracks/Suzuka/baseline").json()["active"]["name"] == "Manual setup"


def test_make_baseline_round_trip_stores_confidence(empty_client):
    empty_client.post("/api/tracks/Spielberg/baseline", json={"setup": SPIELBERG, "source": "manual"})
    g = _gen(empty_client)
    values = {k: v["value"] for k, v in g["setup"].items()}
    meta = {"confidence": {k: v["confidence"] for k, v in g["setup"].items()}, "first_test": g["first_test"]}
    r = empty_client.post("/api/tracks/Suzuka/baseline", json={"setup": values, "source": "generator", "name": "Generated 2026-10-15", "meta": meta})
    assert r.status_code == 200, r.text
    active = r.json()["active"]
    assert active["source"] == "generator" and active["name"] == "Generated 2026-10-15"
    assert active["meta"]["confidence"]["wing_setup_0"] == g["setup"]["wing_setup_0"]["confidence"]
    assert active["meta"]["first_test"]["key"] == g["first_test"]["key"]
    shown = {d["key"]: d["value"] for d in active["display"]}
    assert shown["wing_setup_0"] == g["setup"]["wing_setup_0"]["display"] and shown["fuel_setup"] == g["fuel"]["race_kg"]


def test_target_tracks_own_settled_value_is_absolute(empty_client, tmp_path):
    engineer_log.ensure_engineer_schema(tmp_path)
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO engineer_settled (track, param, value, updated_at) VALUES ('Suzuka', 'arb_setup_0', 5, '2026-10-01T00:00:00+00:00')")
    arb = _gen(empty_client)["setup"]["arb_setup_0"]
    item = arb["evidence"][0]
    assert item["track"] == "Suzuka" and item["value"] == 5 and item["offset"] is None and item["similarity"] == 1.0
    assert arb["value"] < prior_for("Suzuka")[0]["arb_setup_0"]
