"""Tyre-set inventory store."""

from __future__ import annotations

from telemetry.tyre_inventory import available_wear, clear_inventory, get_inventory, save_inventory


def test_round_trip_and_latest_wins(tmp_path):
    assert get_inventory("Monza", tmp_path) is None
    sets = [{"compound": 18, "wear": 0, "available": True, "fitted": False},
            {"compound": 18, "wear": 34, "available": True, "fitted": True},
            {"compound": 0, "wear": 0, "available": False, "fitted": False}]
    save_inventory("Monza", sets, session_type="Qualifying", app_root=tmp_path)
    inv = get_inventory("Monza", tmp_path)
    assert inv["source"] == "game" and inv["session_type"] == "Qualifying" and len(inv["sets"]) == 2
    save_inventory("Monza", [{"compound": 19, "wear": 5}], source="manual", app_root=tmp_path)
    inv = get_inventory("Monza", tmp_path)
    assert inv["source"] == "manual" and inv["sets"][0]["compound"] == 19 and inv["sets"][0]["available"]
    clear_inventory("Monza", tmp_path)
    assert get_inventory("Monza", tmp_path) is None


def test_available_wear_filters_and_sorts():
    sets = [{"compound": 18, "wear": 40, "available": True, "fitted": False},
            {"compound": 18, "wear": 0, "available": True, "fitted": False},
            {"compound": 18, "wear": 10, "available": True, "fitted": True},
            {"compound": 19, "wear": 0, "available": False, "fitted": False},
            {"compound": 20, "wear": 150, "available": True}]
    assert available_wear(sets) == {18: [0.0, 10.0, 40.0], 20: [100.0]}
    assert available_wear(sets, exclude_fitted=True) == {18: [0.0, 40.0], 20: [100.0]}
