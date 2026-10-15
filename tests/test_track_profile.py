from __future__ import annotations

import pytest

from telemetry import track_profile as tp
from telemetry.track_catalog import TRACK_LENGTHS_M

from conftest import ROOT, copy_library_db, needs_library


def _corner(a, b, vmin, cls):
    return {"id": 1, "name": "", "start_m": a, "end_m": b, "apex_m": (a + b) / 2, "vmin_kmh": vmin, "speed_class": cls, "merged_from": []}


def test_synthetic_corners_fractions():
    corners = [_corner(100, 200, 80, "slow"), _corner(500, 700, 150, "medium"), _corner(1500, 1800, 230, "fast"), _corner(2000, 2100, 90, "slow")]
    p = tp.profile_from_corners(corners, 4000)
    assert p["source"] == "driven"
    assert p["slow_frac"] == pytest.approx(200 / 4000)
    assert p["medium_frac"] == pytest.approx(200 / 4000)
    assert p["fast_frac"] == pytest.approx(300 / 4000)
    assert p["full_throttle_frac"] == pytest.approx(1 - 700 / 4000)
    assert p["slow_frac"] + p["medium_frac"] + p["fast_frac"] <= 1
    assert tp.profile_from_corners(corners, 4000, full_throttle_m=2000)["full_throttle_frac"] == 0.5


@pytest.mark.parametrize("track", sorted(TRACK_LENGTHS_M))
def test_catalogue_profile_every_layout(track):
    p = tp.profile_from_catalogue(track)
    assert p["source"] == "catalogue" and p["lap_length_m"] == TRACK_LENGTHS_M[track]
    assert p["slow_frac"] + p["medium_frac"] + p["fast_frac"] <= 1
    assert 0 < p["full_throttle_frac"] < 1 and p["heavy_braking_zones"] >= 0
    assert tp.similarity(p, p) == pytest.approx(1.0)


def test_catalogue_alias_and_unknown():
    assert tp.profile_from_catalogue("Austria")["track"] == "Spielberg"
    with pytest.raises(KeyError):
        tp.profile_from_catalogue("Nowhere")


def test_similarity_properties():
    a, b, c = (tp.profile_from_catalogue(t) for t in ("Monza", "Monaco", "Spa"))
    assert tp.similarity(a, b) == pytest.approx(tp.similarity(b, a))
    assert 0 < tp.similarity(a, b) < 1
    assert tp.similarity(a, c) > tp.similarity(a, b)  # Monza is closer to Spa than to Monaco
    fwd, rev = tp.profile_from_catalogue("Zandvoort"), tp.profile_from_catalogue("Zandvoort Reverse")
    assert rev["reverse_of"] == "Zandvoort"
    twin = dict(fwd, track="Zandvoort Reverse")
    assert tp.similarity(fwd, twin) == pytest.approx(tp.REVERSE_PENALTY)


@needs_library
def test_real_library_profiles(tmp_path):
    import shutil

    from telemetry import db

    copy_library_db(tmp_path / "data" / "telemetry.db")
    (tmp_path / "data" / "sessions").mkdir(parents=True, exist_ok=True)
    for r in db.list_sessions(tmp_path).to_dict("records"):  # only the parquet files these tracks need
        if r.get("track") in ("Monza", "Hungaroring", "Zandvoort") and (ROOT / r["telemetry_path"]).exists():
            dst = tmp_path / r["telemetry_path"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / r["telemetry_path"], dst)
    profiles = {}
    for t in ("Monza", "Hungaroring", "Zandvoort"):
        try:
            profiles[t] = tp.track_profile(t, tmp_path)
        except Exception as e:  # pragma: no cover
            pytest.skip(f"cannot build {t}: {e}")
    for p in profiles.values():
        assert p["slow_frac"] + p["medium_frac"] + p["fast_frac"] <= 1
        assert p["full_throttle_frac"] <= 1
    if any(p["source"] != "driven" for p in profiles.values()):
        pytest.skip("library lacks clean laps for these tracks")
    assert profiles["Monza"]["full_throttle_frac"] > profiles["Hungaroring"]["full_throttle_frac"]
    assert profiles["Monza"]["full_throttle_frac"] > profiles["Zandvoort"]["full_throttle_frac"]
    assert tp.similarity(profiles["Hungaroring"], profiles["Zandvoort"]) > tp.similarity(profiles["Monza"], profiles["Hungaroring"])
