"""Analysis endpoints (channels, compare, map, inventory) on the Bahrain race, in a temporary library."""

from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def laps(client, race_id) -> pd.DataFrame:
    body = client.get(f"/api/sessions/{race_id}").json()
    return pd.DataFrame(body["laps"]).set_index("lap")


def _clean_laps(laps: pd.DataFrame) -> list[int]:
    return [int(lap) for lap in laps.index[(laps["lap_class"] == "push")]]


def test_channels_default_set(client, race_id, laps):
    lap = _clean_laps(laps)[0]
    body = client.get(f"/api/sessions/{race_id}/laps/{lap}/channels").json()
    assert body["session_id"] == race_id and body["lap"] == lap
    assert body["x_label"] == "Distance (m)"
    assert list(body["channels"]) == ["speed", "throttle", "brake", "gear", "rpm", "steering", "lap_time"]
    n = len(body["x"])
    assert n > 1000 and all(len(v) == n for v in body["channels"].values())
    assert body["units"]["speed"] == "km/h" and body["units"]["lap_time"] == "s"
    assert any(v is not None for v in body["channels"]["speed"])


def test_channels_selection_and_step(client, race_id, laps):
    lap = _clean_laps(laps)[0]
    url = f"/api/sessions/{race_id}/laps/{lap}/channels"
    fine = client.get(url, params={"channels": "speed,g_lat", "step": 2}).json()
    coarse = client.get(url, params={"channels": "speed", "step": 10}).json()
    assert list(fine["channels"]) == ["speed", "g_lat"]
    assert len(coarse["x"]) < len(fine["x"])
    assert coarse["x"][1] - coarse["x"][0] == 10


def test_channels_errors(client, race_id, laps):
    lap = _clean_laps(laps)[0]
    assert client.get(f"/api/sessions/{race_id}/laps/{lap}/channels", params={"channels": "nope"}).status_code == 400
    assert client.get(f"/api/sessions/{race_id}/laps/9999/channels").status_code == 404
    assert client.get(f"/api/sessions/999999/laps/{lap}/channels").status_code == 404


def test_compare_final_delta_matches_lap_time_gap(client, race_id, laps):
    push = laps.loc[_clean_laps(laps)]
    ref_lap, lap = int(push["lap_time"].idxmin()), int(push["lap_time"].idxmax())
    body = client.get(f"/api/sessions/{race_id}/compare", params={"lap": lap, "ref_lap": ref_lap}).json()
    n = len(body["lap_distance"])
    for key in ("ref_speed", "cmp_speed", "ref_throttle", "cmp_brake", "cmp_gear", "cmp_steering", "cmp_rpm", "delta_time"):
        assert len(body[key]) == n, key
    gap = float(laps.loc[lap, "lap_time"] - laps.loc[ref_lap, "lap_time"])
    assert body["final_delta"] == pytest.approx(gap, abs=0.05)
    assert len(body["sectors"]) == 3 and len(body["mini_sectors"]) == 12
    assert {"sector", "delta_s"} <= set(body["sectors"][0])
    assert "mini_sector" in body["mini_sectors"][0]
    assert body["ref_session"] == race_id


def test_compare_other_session_and_errors(client, race_id, laps):
    lap = _clean_laps(laps)[0]
    same = client.get(f"/api/sessions/{race_id}/compare", params={"lap": lap, "ref_lap": lap, "ref_session": race_id})
    assert same.status_code == 200 and abs(same.json()["final_delta"]) < 1e-6
    assert client.get(f"/api/sessions/{race_id}/compare", params={"lap": lap, "ref_lap": 9999}).status_code == 404
    assert client.get(f"/api/sessions/{race_id}/compare", params={"lap": lap, "ref_lap": lap, "ref_session": 999999}).status_code == 404


def test_map_payload(client, race_id, laps):
    push = _clean_laps(laps)
    body = client.get(f"/api/sessions/{race_id}/map", params={"lap": push[0], "ref_lap": push[1], "color": "delta"}).json()
    n = len(body["x"])
    assert n > 1000 and len(body["y"]) == n and len(body["d"]) == n
    labels = {c["label"] for c in body["channels"]}
    assert {"Speed", "Throttle", "Δt"} <= labels
    assert all(len(c["values"]) == n for c in body["channels"])
    assert body["color"]["label"].startswith("Δt")
    assert body["spans"] and body["labels"]
    assert body["track"] and body["track_length"] > 1000
    solo = client.get(f"/api/sessions/{race_id}/map", params={"lap": push[0]}).json()
    assert solo["color"]["label"].startswith("speed") and "ref" not in solo["channels"][0]
    assert client.get(f"/api/sessions/{race_id}/map", params={"lap": push[0], "color": "x"}).status_code == 400
    assert client.get(f"/api/sessions/{race_id}/map", params={"lap": 9999}).status_code == 404


def test_map_reference_session(client, race_id, laps):
    push = _clean_laps(laps)
    base = {"lap": push[0], "ref_lap": push[1], "color": "delta"}
    own = client.get(f"/api/sessions/{race_id}/map", params=base).json()
    explicit = client.get(f"/api/sessions/{race_id}/map", params={**base, "ref_session": race_id}).json()
    assert own["ref_session"] == explicit["ref_session"] == race_id
    assert explicit["channels"][-1]["values"] == own["channels"][-1]["values"]
    assert client.get(f"/api/sessions/{race_id}/map", params={**base, "ref_session": 999999}).status_code == 404


def test_channel_inventory(client, race_id):
    rows = client.get(f"/api/sessions/{race_id}/channels/inventory").json()
    assert rows and {"Group", "Channel", "Unit", "Columns"} <= set(rows[0])
    assert any(r["Channel"] == "Speed" and r["Columns"] == "speed" for r in rows)
    assert client.get("/api/sessions/999999/channels/inventory").status_code == 404
