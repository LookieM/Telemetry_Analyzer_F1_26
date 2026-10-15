"""Corner detection and the per-corner report: synthetic laps for the rules, real sessions for plausibility."""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
import pytest

from conftest import DB_PATH, ROOT, needs_library
from telemetry.corner_detect import detect_corners, speed_class
from telemetry.corner_report import callouts, corner_report

# ------------------------------------------------------------------ synthetic laps


def make_lap(length: int, corners: list[dict], base: float = 250.0, lap_seconds: float = 60.0) -> pd.DataFrame:
    """A lap on a 1 m grid: `base` km/h, throttle full, plus corners given as
    {apex, vmin, entry (m of braking before the apex), exit (m of partial throttle after it), brake (bool)}."""
    d = np.arange(0, length + 1, dtype=float)
    speed = np.full_like(d, base)
    throttle = np.ones_like(d)
    brake = np.zeros_like(d)
    for c in corners:
        a, e = c["apex"] - c["entry"], c["apex"] + c["exit"]
        inside = (d >= a) & (d <= e)
        speed = np.where(inside, np.minimum(speed, np.interp(d, [a, c["apex"], e], [base, c["vmin"], base])), speed)
        throttle[inside & (d <= c["apex"])] = 0.0
        throttle[inside & (d > c["apex"])] = 0.6
        if c.get("brake", True):
            brake[(d >= a) & (d <= c["apex"] - c["entry"] * 0.3)] = 0.9
    slow = 1.0 / np.maximum(speed, 1)
    t = np.cumsum(slow / slow.sum() * lap_seconds)
    return pd.DataFrame({"lap_distance": d, "speed": speed, "throttle": throttle, "brake": brake, "lap_time": t})


def test_two_separate_corners_are_found_with_apex_and_class():
    lap = make_lap(3000, [{"apex": 800, "vmin": 90, "entry": 120, "exit": 100}, {"apex": 2000, "vmin": 150, "entry": 100, "exit": 90}])
    found = detect_corners(lap)
    assert [c["name"] for c in found] == ["T1", "T2"]
    assert abs(found[0]["apex_m"] - 800) < 6 and abs(found[1]["apex_m"] - 2000) < 6
    assert [c["speed_class"] for c in found] == ["slow", "medium"]
    assert found[0]["start_m"] < 700 + 25 and found[0]["end_m"] > 880
    assert all(c["merged_from"] == [] for c in found)


def test_complex_without_full_throttle_between_the_minima_is_one_corner():
    lap = make_lap(3000, [{"apex": 1000, "vmin": 110, "entry": 120, "exit": 60}, {"apex": 1130, "vmin": 90, "entry": 70, "exit": 90}])
    found = detect_corners(lap)
    assert len(found) == 1
    assert len(found[0]["merged_from"]) == 2
    assert abs(found[0]["apex_m"] - 1130) < 6  # the deepest minimum
    assert found[0]["vmin_kmh"] < 95


def test_full_throttle_between_the_minima_keeps_two_corners():
    lap = make_lap(3000, [{"apex": 1000, "vmin": 110, "entry": 100, "exit": 60}, {"apex": 1400, "vmin": 90, "entry": 100, "exit": 90}])
    assert len(detect_corners(lap)) == 2


def test_flat_kink_is_not_a_corner():
    lap = make_lap(3000, [{"apex": 800, "vmin": 90, "entry": 120, "exit": 100}])
    kink = (lap["lap_distance"] > 1900) & (lap["lap_distance"] < 2100)
    lap.loc[kink, "speed"] -= 2.0 * np.sin(np.pi * (lap.loc[kink, "lap_distance"] - 1900) / 200)  # 2 km/h dip, throttle stays full
    found = detect_corners(lap)
    assert len(found) == 1 and abs(found[0]["apex_m"] - 800) < 6


def test_unknown_track_numbers_corners_from_the_start_line():
    lap = make_lap(3000, [{"apex": a, "vmin": 100, "entry": 100, "exit": 80} for a in (600, 1300, 2200)])
    assert [c["name"] for c in detect_corners(lap, catalogue=None)] == ["T1", "T2", "T3"]


def test_catalogue_names_follow_the_nearest_apex_and_merge_ranges():
    lap = make_lap(
        3000,
        [
            {"apex": 600, "vmin": 100, "entry": 100, "exit": 80},
            {"apex": 1500, "vmin": 90, "entry": 90, "exit": 60},
            {"apex": 1620, "vmin": 95, "entry": 40, "exit": 80},
        ],
    )
    catalogue = [
        {"id": "SF", "name": "Start/Finish", "start_frac": 0.0, "end_frac": 0.1, "kind": "straight"},
        {"id": "T1", "name": "T1 Big", "start_frac": 0.1, "end_frac": 0.3, "kind": "corner", "apex_frac": 0.2},
        {"id": "T2-3", "name": "T2–T3", "start_frac": 0.4, "end_frac": 0.6, "kind": "corner", "apex_frac": 0.5},
        {"id": "T4", "name": "T4", "start_frac": 0.5, "end_frac": 0.6, "kind": "corner", "apex_frac": 0.54},
    ]
    found = detect_corners(lap, catalogue, 3000)
    assert [c["name"] for c in found] == ["T1 Big", "T2–T4"]


def test_speed_classes():
    assert [speed_class(v) for v in (80, 119.9, 120, 200, 201)] == ["slow", "slow", "medium", "medium", "fast"]


def test_report_deltas_add_up_and_callouts_name_the_measured_difference():
    spec = [{"apex": 800, "vmin": 90, "entry": 120, "exit": 100}, {"apex": 2000, "vmin": 150, "entry": 100, "exit": 90}]
    ref = make_lap(3000, spec, lap_seconds=60.0)
    # focus: brakes 15 m earlier into corner 1, is 8 km/h slower there, and 0.4 s slower overall
    focus = make_lap(3000, [{"apex": 800, "vmin": 82, "entry": 135, "exit": 100}, spec[1]], lap_seconds=60.4)
    rep = corner_report(focus, ref, detect_corners(ref))
    assert rep["lap_delta"] == pytest.approx(0.4, abs=0.05)
    assert rep["sum_corner_delta"] + rep["straights_delta"] == pytest.approx(rep["lap_delta"] - rep["start_delta"], abs=0.02)
    c1 = rep["corners"][0]
    assert c1["delta"]["brake_m"] == pytest.approx(-15, abs=3)
    assert c1["delta"]["vmin_kmh"] == pytest.approx(-8, abs=1.5)
    text = c1["callouts"][0]
    assert "brake" in text and "earlier" in text and "vmin −" in text


def test_callouts_stay_silent_below_the_noise():
    quiet = {"time_s": 0.02, "brake_m": 12.0, "vmin_kmh": -6.0, "exit_kmh": None, "throttle_m": None}
    assert callouts("T4", quiet) == []
    assert callouts("T4", {**quiet, "time_s": 0.08}) == ["T4: brake 12 m later, vmin −6 km/h, +0.08 s"]
    flat = {"time_s": -0.05, "brake_m": 1.0, "vmin_kmh": 0.5, "exit_kmh": 0.0, "throttle_m": 2.0}
    assert "no clear difference" in callouts("T4", flat)[0]


# ------------------------------------------------------------------ real sessions

TRACKS = ("Austria", "Hungaroring", "Monza", "Miami")
_CACHE: dict[int, list[pd.DataFrame]] = {}


def _library_sessions(track: str) -> list[dict]:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute("SELECT * FROM sessions WHERE track = ? ORDER BY id", (track,))]
    finally:
        con.close()


def _clean_laps(session: dict, n: int = 3) -> list[pd.DataFrame]:
    """The n fastest full-length clean laps of a library session (frames with the report columns)."""
    import pyarrow.parquet as pq

    from telemetry.corner_store import FRAME_COLUMNS, clean_laps
    from telemetry.metrics import get_lap

    if session["id"] not in _CACHE:
        path = ROOT / session["telemetry_path"]
        present = set(pq.read_schema(path).names)
        df = pd.read_parquet(path, columns=[c for c in dict.fromkeys(FRAME_COLUMNS) if c in present])
        _CACHE[session["id"]] = [get_lap(df, int(r.lap)) for r in clean_laps(df).head(n).itertuples()]
    return _CACHE[session["id"]]


def _real_cases():
    from telemetry.corners import normalize_track_name
    from telemetry.track_catalog import TRACK_CORNERS_FRAC, TRACK_LENGTHS_M

    if not DB_PATH.exists():
        return []
    cases = []
    for track in TRACKS:
        key = normalize_track_name(track)
        for s in _library_sessions(track):
            cases.append(pytest.param(s, TRACK_CORNERS_FRAC.get(key), TRACK_LENGTHS_M.get(key), id=f"{track}-{s['id']}"))
    return cases


REAL_CASES = _real_cases()


@needs_library
@pytest.mark.parametrize("session,catalogue,length", REAL_CASES)
def test_real_session_corners_are_plausible(session, catalogue, length):
    laps = _clean_laps(session)
    if len(laps) < 2:
        pytest.skip("fewer than two clean laps")
    corners = detect_corners(laps[0], catalogue, length)
    assert 3 <= len(corners) <= 20
    assert all(a["end_m"] <= b["start_m"] for a, b in zip(corners, corners[1:]))
    # The reference lap against itself: every brake point inside its corner window, vmin <= entry / exit.
    own = corner_report(laps[0], laps[0], corners)
    for c in own["corners"]:
        f = c["focus"]
        if f["brake_m"] is not None:
            assert c["start_m"] <= f["brake_m"] <= c["end_m"], c["name"]
        assert f["vmin_kmh"] <= f["entry_kmh"] and f["vmin_kmh"] <= f["exit_kmh"], c["name"]
        assert c["delta"]["time_s"] == pytest.approx(0, abs=1e-6)
    # Another clean lap against it: brake points stay within the look-back, deltas add up to the lap delta.
    rep = corner_report(laps[1], laps[0], corners)
    for c in rep["corners"]:
        b = c["focus"]["brake_m"]
        if b is not None:
            assert c["start_m"] - 60 <= b <= c["end_m"], c["name"]
    assert rep["sum_corner_delta"] + rep["straights_delta"] == pytest.approx(rep["lap_delta"] - rep["start_delta"], abs=0.02)
    t_focus, t_ref = float(laps[1]["lap_time"].max()), float(laps[0]["lap_time"].max())
    assert rep["lap_delta"] == pytest.approx(t_focus - t_ref, abs=0.1)


@needs_library
def test_real_corner_count_is_stable_between_the_two_best_laps_of_a_session():
    equal = total = 0
    for case in REAL_CASES:
        session, catalogue, length = case.values
        laps = _clean_laps(session)
        if len(laps) < 2:
            continue
        n0, n1 = (len(detect_corners(laps[i], catalogue, length)) for i in (0, 1))
        assert abs(n0 - n1) <= 1, f"session {session['id']}: {n0} vs {n1}"
        total += 1
        equal += n0 == n1
    if total:
        assert equal / total >= 0.8, f"corner count equal in only {equal} of {total} sessions"
