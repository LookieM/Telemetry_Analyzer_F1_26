"""Corner endpoints on the Bahrain race in a temporary library (never the real data/)."""

from __future__ import annotations

import shutil

import pandas as pd
import pytest

from conftest import ROOT, session_by_source


@pytest.fixture
def laps(client, race_id) -> list[int]:
    body = client.get(f"/api/sessions/{race_id}").json()
    frame = pd.DataFrame(body["laps"])
    return [int(lap) for lap in frame.loc[frame["lap_class"] == "push", "lap"]]


def test_corners_shape_and_delta_bookkeeping(client, race_id, laps):
    body = client.get(f"/api/sessions/{race_id}/corners", params={"lap": laps[1], "ref_lap": laps[0]}).json()
    assert body["track"] == "Bahrain" and body["lap"] == laps[1]
    assert body["reference"] == {"session": race_id, "lap": laps[0]}
    assert body["corners_source"]["session"] == race_id
    assert len(body["corners"]) >= 5
    c = body["corners"][0]
    for key in ("id", "name", "start_m", "end_m", "apex_m", "vmin_kmh", "speed_class", "merged_from", "focus", "ref", "delta", "phases", "callouts"):
        assert key in c
    for key in ("time_s", "entry_kmh", "vmin_kmh", "exit_kmh", "brake_m", "trail_m", "throttle_m"):
        assert key in c["focus"] and key in c["ref"] and key in c["delta"]
    assert set(c["phases"]) == {"entry", "mid", "exit"}
    assert c["speed_class"] in ("slow", "medium", "fast")
    assert body["sum_corner_delta"] + body["straights_delta"] == pytest.approx(body["lap_delta"] - body["start_delta"], abs=0.02)
    starts = [x["start_m"] for x in body["corners"]]
    assert starts == sorted(starts)


def test_corners_default_to_the_best_lap_against_itself(client, race_id):
    body = client.get(f"/api/sessions/{race_id}/corners").json()
    assert body["lap"] == body["reference"]["lap"]
    assert all(abs(c["delta"]["time_s"]) < 1e-6 for c in body["corners"])
    assert all(c["callouts"] == [] for c in body["corners"])


def test_corners_unknown_session_or_lap_is_404(client, race_id):
    assert client.get("/api/sessions/99999/corners").status_code == 404
    assert client.get(f"/api/sessions/{race_id}/corners", params={"lap": 9999}).status_code == 404
    assert client.get(f"/api/sessions/{race_id}/corners", params={"ref_lap": 9999}).status_code == 404
    assert client.get(f"/api/sessions/{race_id}/corners", params={"ref_session": 99999}).status_code == 404


def test_corners_bad_parameters_are_422(client, race_id):
    assert client.get(f"/api/sessions/{race_id}/corners", params={"lap": "x"}).status_code == 422


def _add_other_track(lib_root) -> int:
    """Copy one non-Bahrain session of the personal library into the tmp library; its id."""
    session = session_by_source("Austria_race.csv")
    src = ROOT / session["telemetry_path"]
    shutil.copy2(src, lib_root / "data" / "sessions" / src.name)
    return int(session["id"])


def test_reference_session_must_be_on_the_same_track(client, lib_root, race_id):
    other = _add_other_track(lib_root)
    r = client.get(f"/api/sessions/{race_id}/corners", params={"ref_session": other})
    assert r.status_code == 422 and "not on Bahrain" in r.json()["detail"]


def test_rebuild_replaces_the_stored_corners(client, lib_root, race_id, laps):
    first = client.get("/api/tracks/Bahrain/corners").json()
    assert first["source_session"] == race_id
    r = client.post("/api/tracks/Bahrain/corners/rebuild", json={"session": race_id, "lap": laps[1]})
    assert r.status_code == 200
    rebuilt = r.json()
    assert rebuilt["source_lap"] == laps[1] and len(rebuilt["corners"]) >= 5
    assert client.get("/api/tracks/Bahrain/corners").json()["source_lap"] == laps[1]
    body = client.get(f"/api/sessions/{race_id}/corners").json()
    assert body["corners_source"]["lap"] == laps[1]


def test_rebuild_error_paths(client, lib_root, race_id):
    url = "/api/tracks/Bahrain/corners/rebuild"
    assert client.post(url, json={"session": 99999, "lap": 1}).status_code == 404
    assert client.post(url, json={"session": race_id, "lap": 9999}).status_code == 404
    assert client.post(url, json={"session": race_id}).status_code == 422
    other = _add_other_track(lib_root)
    r = client.post(url, json={"session": other, "lap": 1})
    assert r.status_code == 422 and "not on Bahrain" in r.json()["detail"]


def test_track_without_any_session_has_no_corners(empty_client):
    assert empty_client.get("/api/tracks/Bahrain/corners").status_code == 404


# ------------------------------------------------------------------ balance


@pytest.fixture
def full_export_id(lib_root) -> int:
    """The Austria race (full export with slip channels) copied into the tmp library."""
    return _add_other_track(lib_root)


def test_compact_import_says_why_it_has_no_balance(client, race_id, laps):
    body = client.get(f"/api/sessions/{race_id}/corners", params={"lap": laps[1], "ref_lap": laps[0]}).json()
    assert body["balance_available"] is False and "slip" in body["balance_reason"]
    assert body["balance_summary"] is None and body["lockups"] == []
    assert all(c["balance"] is None for c in body["corners"])
    bal = client.get(f"/api/sessions/{race_id}/balance").json()
    assert bal["balance_available"] is False
    assert bal["balance_reason"] and bal["corners"] == [] and bal["laps"] == 0


def test_corners_rows_carry_balance_on_a_full_export(client, full_export_id):
    body = client.get(f"/api/sessions/{full_export_id}/corners").json()
    assert body["balance_available"] is True and body["balance_reason"] is None
    assert set(body["balance_baseline"]) == {"entry", "mid", "exit"}
    assert isinstance(body["balance_summary"], str) and body["balance_summary"]
    for c in body["corners"]:
        assert set(c["balance"]) == {"entry", "mid", "exit", "traction", "lockups"}
    assert any(c["balance"]["mid"] is not None for c in body["corners"])
    for lock in body["lockups"]:
        assert set(lock) >= {"wheel", "distance_m", "length_m", "corner"}
        assert lock["wheel"] in ("FL", "FR", "RL", "RR")


def test_balance_endpoint_is_the_median_over_clean_laps(client, full_export_id):
    body = client.get(f"/api/sessions/{full_export_id}/balance").json()
    assert body["track"] == "Spielberg" and body["balance_available"] is True
    assert body["laps"] >= 3 and len(body["lap_numbers"]) == body["laps"]
    corners = client.get("/api/tracks/Spielberg/corners").json()["corners"]
    assert [c["id"] for c in body["corners"]] == [c["id"] for c in corners]
    row = body["corners"][0]
    assert set(row) >= {"id", "name", "speed_class", "entry", "mid", "exit", "traction", "lockups"}
    assert all("lap" in lock for lock in body["lockups"])


def test_balance_error_paths(client):
    assert client.get("/api/sessions/99999/balance").status_code == 404
    assert client.get("/api/sessions/x/balance").status_code == 422
