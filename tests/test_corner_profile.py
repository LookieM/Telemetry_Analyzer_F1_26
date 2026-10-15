"""Corner profile of one lap: synthetic frame for exact numbers, a real library lap for plausibility."""

from __future__ import annotations

import numpy as np
import pandas as pd

from conftest import ROOT, needs_library, session_by_source
from test_corner_balance import CORNERS, make_frame
from telemetry.corner_profile import corner_profile, frame_coverage


def timed(frame: pd.DataFrame, speed_ms: float = 50.0) -> pd.DataFrame:
    return frame.assign(lap_time=frame["lap_distance"] / speed_ms)


def test_times_are_distance_over_speed_and_phases_add_up():
    prof = corner_profile(timed(make_frame(6.0, 3.0)), CORNERS)
    assert set(prof) == {1, 2}
    c = prof[1]
    assert abs(c["time_s"] - 200.0 / 50.0) < 0.05
    assert abs(sum(c["phases"].values()) - c["time_s"]) < 0.05
    assert c["name"] == "T1" and c["speed_class"] == "slow"
    assert all(abs(c["understeer"][p] - 3.0) < 0.1 for p in ("entry", "mid"))
    assert c["traction"] is not None and 0.0 < c["traction"] <= 0.05


def test_without_slip_channels_times_stay_and_balance_is_none():
    prof = corner_profile(timed(make_frame(with_slip=False)), CORNERS)
    assert prof[1]["time_s"] > 0
    assert prof[1]["understeer"] == {"entry": None, "mid": None, "exit": None} and prof[1]["traction"] is None


def test_corners_outside_the_frame_are_left_out_and_coverage_is_a_share():
    f = timed(make_frame())
    f = f[f["lap_distance"] < 600]
    assert set(corner_profile(f, CORNERS)) == {1}
    assert abs(frame_coverage(f, 1000.0) - 0.599) < 0.01
    assert frame_coverage(f, None) == 0.0 and frame_coverage(pd.DataFrame(), 1000.0) == 0.0


@needs_library
def test_real_library_lap_has_a_plausible_profile():
    from telemetry import corner_store
    from telemetry.corner_detect import detect_corners
    from telemetry.metrics import get_lap
    from telemetry.track_catalog import TRACK_CORNERS_FRAC, TRACK_LENGTHS_M

    df = pd.read_parquet(ROOT / session_by_source("Austria_practice.csv")["telemetry_path"])
    lap = get_lap(df, int(corner_store.clean_laps(df).iloc[0]["lap"]))
    corners = detect_corners(lap, TRACK_CORNERS_FRAC.get("Spielberg"), TRACK_LENGTHS_M.get("Spielberg"))
    prof = corner_profile(lap, corners)
    assert len(prof) == len(corners)
    total = sum(p["time_s"] for p in prof.values())
    assert 10 < total < float(lap["lap_time"].max())
    assert all(p["time_s"] > 0.3 for p in prof.values())
