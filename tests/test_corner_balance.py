"""Balance per corner and phase: synthetic frames for sign / magnitude / lock-ups, real sessions for plausibility."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from conftest import ROOT, needs_library, session_by_source
from telemetry.corner_balance import (
    NEUTRAL_DEG,
    balance_label,
    balance_summary,
    has_slip_channels,
    lap_balance,
    relative_index,
    session_balance,
)

CORNERS = [
    {"id": 1, "name": "T1", "start_m": 300.0, "end_m": 500.0, "apex_m": 400.0, "speed_class": "slow"},
    {"id": 2, "name": "T2", "start_m": 700.0, "end_m": 850.0, "apex_m": 780.0, "speed_class": "fast"},
]


def make_frame(front_deg: float = 6.0, rear_deg: float = 3.0, with_slip: bool = True) -> pd.DataFrame:
    """A 1 m lap with cornering (1.5 g) inside the corner windows and straight line outside."""
    d = np.arange(0, 1000.0)
    inside = np.zeros_like(d, dtype=bool)
    for c in CORNERS:
        inside |= (d >= c["start_m"]) & (d <= c["end_m"])
    f = pd.DataFrame(
        {
            "lap": 1,
            "lap_distance": d,
            "throttle": np.where(inside, 0.7, 1.0),
            "brake": 0.0,
            "steering": np.where(inside, 0.3, 0.0),
            "g_lat": np.where(inside, 1.5, 0.0),
        }
    )
    if with_slip:
        for i in range(4):
            f[f"wheel_slip_angle_{i}"] = np.where(inside, np.radians(front_deg if i < 2 else rear_deg), 0.0)
            f[f"wheel_slip_ratio_{i}"] = np.where(inside, 0.05, 0.0)
    return f


def test_front_slipping_more_than_rear_is_positive_understeer_in_degrees():
    out = lap_balance(make_frame(6.0, 3.0), CORNERS)
    assert out["available"]
    row = out["corners"][0]
    assert row["entry"] == pytest.approx(3.0, abs=1e-6) and row["mid"] == pytest.approx(3.0, abs=1e-6) and row["exit"] == pytest.approx(3.0, abs=1e-6)


def test_rear_slipping_more_than_front_is_negative_and_slip_sign_does_not_matter():
    frame = make_frame(2.0, 7.0)
    frame["wheel_slip_angle_2"] = -frame["wheel_slip_angle_2"]  # the sign of a slip angle is only its direction
    row = lap_balance(frame, CORNERS)["corners"][0]
    assert row["mid"] == pytest.approx(-5.0, abs=1e-6)


def test_only_front_first_wheel_order_counts():
    frame = make_frame(4.0, 4.0)
    frame["wheel_slip_angle_0"] = np.radians(10.0) * (frame["g_lat"] > 0)  # FL only, in the corners
    row = lap_balance(frame, CORNERS)["corners"][0]
    assert row["mid"] == pytest.approx((10 + 4) / 2 - 4, abs=1e-6)


def test_samples_without_cornering_do_not_count():
    frame = make_frame(6.0, 3.0)
    frame["g_lat"] = 0.2  # below the cornering threshold everywhere
    row = lap_balance(frame, CORNERS)["corners"][0]
    assert row["entry"] is None and row["mid"] is None and row["exit"] is None


def test_steering_stands_in_when_lateral_g_is_missing():
    frame = make_frame(6.0, 3.0).drop(columns=["g_lat"])
    assert lap_balance(frame, CORNERS)["corners"][0]["mid"] == pytest.approx(3.0, abs=1e-6)


def test_traction_is_rear_slip_ratio_on_the_throttle_in_the_exit_window():
    frame = make_frame()
    exit_zone = (frame["lap_distance"] > 420) & (frame["lap_distance"] < 540)
    for i in (2, 3):
        frame.loc[exit_zone, f"wheel_slip_ratio_{i}"] = 0.2
    frame.loc[exit_zone, "wheel_slip_ratio_0"] = 0.9  # front slip never counts
    assert lap_balance(frame, CORNERS)["corners"][0]["traction"] == pytest.approx(0.2, abs=0.02)
    frame["throttle"] = 0.3  # off the throttle: no traction value
    assert lap_balance(frame, CORNERS)["corners"][0]["traction"] is None


def test_lockups_are_found_per_wheel_with_distance_and_corner():
    frame = make_frame()
    frame["brake"] = 0.8
    zone = (frame["lap_distance"] >= 270) & (frame["lap_distance"] < 276)
    frame.loc[zone, "wheel_slip_ratio_1"] = -0.4  # FR, in the braking zone before T1
    frame.loc[(frame["lap_distance"] >= 750) & (frame["lap_distance"] < 760), "wheel_slip_ratio_3"] = -0.3  # RR inside T2
    out = lap_balance(frame, CORNERS)
    assert [(x["wheel"], x["corner"]["name"]) for x in out["lockups"]] == [("FR", "T1"), ("RR", "T2")]
    assert out["lockups"][0]["distance_m"] == 270 and out["lockups"][0]["length_m"] == 5
    assert out["corners"][0]["lockups"] == {"FR": 1} and out["corners"][1]["lockups"] == {"RR": 1}


def test_slip_without_braking_or_one_sample_is_no_lockup():
    frame = make_frame()
    frame.loc[(frame["lap_distance"] >= 270) & (frame["lap_distance"] < 280), "wheel_slip_ratio_0"] = -0.4  # no brake
    frame["brake"] = 0.8
    frame.loc[frame["lap_distance"] == 600, "wheel_slip_ratio_2"] = -0.5  # a single sample
    assert lap_balance(frame, CORNERS)["lockups"] == [
        {"wheel": "FL", "distance_m": 270.0, "length_m": 9.0, "min_slip_ratio": pytest.approx(-0.4), "corner": {"id": 1, "name": "T1"}}
    ]


def test_missing_slip_channels_say_so():
    frame = make_frame(with_slip=False)
    assert not has_slip_channels(frame)
    out = lap_balance(frame, CORNERS)
    assert out["available"] is False and "slip" in out["reason"] and out["corners"] == [] and out["lockups"] == []
    assert session_balance([{**out, "lap": 1}], CORNERS)["available"] is False
    assert session_balance([], CORNERS)["available"] is False


def test_session_balance_is_the_median_over_laps_and_keeps_every_lockup():
    laps = []
    for n, front in enumerate((5.0, 6.0, 20.0), start=1):  # one mistake lap must not decide
        b = lap_balance(make_frame(front, 3.0), CORNERS)
        laps.append({**b, "lap": n})
    out = session_balance(laps, CORNERS)
    assert out["laps"] == 3 and out["corners"][0]["mid"] == pytest.approx(3.0, abs=1e-6)
    frame = make_frame()
    frame["brake"] = 0.8
    frame.loc[(frame["lap_distance"] >= 270) & (frame["lap_distance"] < 276), "wheel_slip_ratio_0"] = -0.4
    laps.append({**lap_balance(frame, CORNERS), "lap": 4})
    out = session_balance(laps, CORNERS)
    assert [(x["lap"], x["wheel"]) for x in out["lockups"]] == [(4, "FL")] and out["corners"][0]["lockups"] == {"FL": 1}


def test_labels_are_relative_to_the_typical_value_of_the_phase():
    assert balance_label(NEUTRAL_DEG["mid"], "mid") == "neutral"
    assert balance_label(NEUTRAL_DEG["mid"] + 1.2, "mid") == "slight understeer"
    assert balance_label(NEUTRAL_DEG["entry"] + 2.5, "entry") == "understeer"
    assert balance_label(NEUTRAL_DEG["exit"] - 1.0, "exit") == "slight oversteer"
    assert balance_label(NEUTRAL_DEG["exit"] - 3.0, "exit") == "oversteer"
    assert balance_label(None, "mid") is None and relative_index(None, "mid") is None


def test_summary_names_phases_classes_and_snap_corners():
    def row(i, entry, mid, exit_):
        return {"id": i, "entry": entry, "mid": mid, "exit": exit_}

    e, m, x = NEUTRAL_DEG["entry"], NEUTRAL_DEG["mid"], NEUTRAL_DEG["exit"]
    rows = [row(1, e, m + 1.5, x - 3.0), row(2, e, m, x)]
    text = balance_summary(rows, CORNERS)
    assert text.startswith("Entry neutral")
    assert "mid slight understeer in slow corners" in text and "mid neutral in fast corners" in text
    assert text.endswith("oversteer on exit T1")
    assert balance_summary([row(1, None, None, None)], CORNERS) == "Not enough cornering samples to say"


# ------------------------------------------------------------------ real sessions


def _balance_of(source: str, track: str = "Spielberg") -> dict:
    from telemetry import corner_store
    from telemetry.metrics import get_lap

    session = session_by_source(source)
    df = pd.read_parquet(ROOT / session["telemetry_path"])
    if not has_slip_channels(df):
        pytest.skip(f"{source} has no slip channels")
    clean = corner_store.clean_laps(df)
    if clean.empty:
        pytest.skip(f"{source} has no clean lap")
    from telemetry.corner_detect import detect_corners
    from telemetry.track_catalog import TRACK_CORNERS_FRAC, TRACK_LENGTHS_M

    src = pd.read_parquet(ROOT / session_by_source("Austria_practice.csv")["telemetry_path"])
    ref_lap = get_lap(src, int(corner_store.clean_laps(src).iloc[0]["lap"]))
    corners = detect_corners(ref_lap, TRACK_CORNERS_FRAC.get(track), TRACK_LENGTHS_M.get(track))
    laps = [{**lap_balance(get_lap(df, int(r.lap)), corners), "lap": int(r.lap)} for r in clean.itertuples()]
    return {"corners": corners, "result": session_balance(laps, corners)}


@needs_library
def test_real_full_export_balance_is_plausible():
    out = _balance_of("Austria_practice.csv")
    result = out["result"]
    assert result["available"] and result["laps"] >= 3
    values = {p: [r[p] for r in result["corners"] if r[p] is not None] for p in ("entry", "mid", "exit")}
    assert all(len(v) >= len(out["corners"]) - 2 for v in values.values())
    # no phase of a normal lap is wildly off: the sign is not "huge understeer everywhere"
    assert all(-3.0 < np.median(v) < 6.0 for v in values.values())
    traction = [r["traction"] for r in result["corners"] if r["traction"] is not None]
    assert traction and all(0 < t < 0.5 for t in traction)


@needs_library
def test_real_compact_import_has_no_balance():
    from telemetry.metrics import get_lap

    session = session_by_source("bahrain_race.csv")
    df = pd.read_parquet(ROOT / session["telemetry_path"])
    out = lap_balance(get_lap(df, int(df["lap"].iloc[len(df) // 2])), CORNERS)
    assert out["available"] is False


@needs_library
def test_real_wet_q1_with_the_open_diff_slips_more_on_exit_than_the_locked_q2_and_q3():
    """Austria Q1 (wet, diff on-throttle 55 %) vs Q2 / Q3 (80 %): the rear slips more on exit with the open diff."""
    q1 = _balance_of("Austria_Q1_wet.csv")["result"]
    others = [_balance_of(name)["result"] for name in ("Austria_Q2.csv", "Austria_Q3.csv")]

    def exit_traction(res: dict) -> float:
        return float(np.median([r["traction"] for r in res["corners"] if r["traction"] is not None]))

    assert exit_traction(q1) > 1.3 * max(exit_traction(o) for o in others)
