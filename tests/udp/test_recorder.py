import warnings
from pathlib import Path

import numpy as np
import pytest

from telemetria_server.udp import srt_columns as cols
from telemetria_server.udp.capture_file import iter_capture
from telemetria_server.udp.recorder import SessionRecorder

CAP = Path(__file__).resolve().parents[2] / "data" / "udp_captures" / "20261009-222554.f1cap"
pytestmark = pytest.mark.skipif(not CAP.exists(), reason="no local capture")


@pytest.fixture(scope="module")
def recorder():
    r = SessionRecorder()
    for i, (t, d) in enumerate(iter_capture(CAP)):
        if r.is_new_session(d) or i > 130_000:  # ~2 laps is enough
            break
        r.feed(d, t)
    return r


def test_frame_shape_and_units(recorder):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        df = recorder.build_frame()
    assert recorder.track_id == 10 and df["track"].iloc[0] == "Spa"
    assert df["lap_number"].min() == 0 and df["trackLength"].iloc[0] == 7007
    for lap, g in df.groupby("lap_number"):
        assert g["bin_index"].is_monotonic_increasing and g["bin_index"].diff().dropna().eq(1).all()
    assert not df[["fuel", "tyre_press_0", "ers_store", "velocity_X"]].isna().any().any()
    assert df["tyre_press_0"].between(1.0e5, 2.5e5).all()      # Pa
    assert df["tyre_wear_0"].between(0, 1).all()                # fraction
    assert df["fuel"].between(0, 110).all()
    assert df["wing_setup_0"].between(0, 50).all()
    assert df["tyre_press_setup_0"].between(1.0e5, 2.5e5).all()
    assert df["diff_onThrottle_setup"].between(0, 1).all()


def test_setup_array_order():
    c = np.zeros(1, dtype=np.dtype([(n, "<f4") for n in (
        "m_frontWing", "m_rearWing", "m_onThrottle", "m_offThrottle", "m_frontCamber", "m_rearCamber",
        "m_frontToe", "m_rearToe", "m_frontSuspension", "m_rearSuspension", "m_frontAntiRollBar",
        "m_rearAntiRollBar", "m_frontSuspensionHeight", "m_rearSuspensionHeight", "m_brakePressure",
        "m_brakeBias", "m_engineBraking", "m_rearLeftTyrePressure", "m_rearRightTyrePressure",
        "m_frontLeftTyrePressure", "m_frontRightTyrePressure", "m_ballast", "m_fuelLoad")]))[0]
    c["m_frontCamber"], c["m_rearCamber"] = -3.5, -2.0
    c["m_frontLeftTyrePressure"], c["m_rearLeftTyrePressure"] = 29.5, 22.5
    s = cols.setup_row(c)
    assert s["camber_setup_0"] == s["camber_setup_1"] < s["camber_setup_2"]
    assert round(s["tyre_press_setup_0"] / cols.PSI_TO_PA, 2) == 29.5
    assert round(s["tyre_press_setup_2"] / cols.PSI_TO_PA, 2) == 22.5


def test_ingest_into_temp_library(recorder, tmp_path):
    res = recorder.ingest(tmp_path)
    assert not res.already_existed and res.track == "Spa" and res.lap_count >= 1
    again = recorder.ingest(tmp_path)
    assert again.already_existed and again.session_id == res.session_id


def _lap_packet_recorder():
    """Recorder with hand-fed context, to test the sampling rules without a capture."""
    r = SessionRecorder()
    r.track_length = 5000.0
    r._ctx["motion"] = {"world_position_X": 0.0}
    return r


def _sample(r, lap_num, dist, t, status=1):
    r._ctx["lapraw"] = {"lap_distance": dist, "lap_time_ms": int(t * 1000), "lap_num": lap_num, "driver_status": status}
    return r._sample()


def test_garage_and_stopped_timer_are_not_recorded():
    r = _lap_packet_recorder()
    assert not _sample(r, 2, 100.0, 0.0)          # timer not running (grid / pit exit before the line)
    assert not _sample(r, 2, 120.0, 5.0, status=0)  # in the garage
    assert _sample(r, 2, 140.0, 6.0, status=3)      # out lap with a running timer
    assert list(r._laps[1]) == [140]


def test_rewind_drops_only_the_future_of_the_lap():
    r = _lap_packet_recorder()
    for k in range(1, 50):
        _sample(r, 3, k * 50.0, k * 1.0)            # lap 2, 50 m per second
    _sample(r, 3, 1000.0, 20.0)                      # flashback to t = 20 s
    kept = r._laps[2]
    assert max(kept) == 1000 and all(row["lap_time"] <= 20.0 for row in kept.values())
    assert 500 in kept                               # the part before the rewind survives
    _sample(r, 2, 4000.0, 80.0)                      # rewound into the previous lap
    assert 2 not in r._laps


def test_integer_channels_are_carried_forward_not_interpolated():
    r = _lap_packet_recorder()
    for k in range(1, 40):  # every 7 m, so the bins in between get filled
        r._ctx["lap"] = {"race_position": 5 if k < 20 else 4}
        _sample(r, 2, k * 7.0, k * 0.1)
    df = r.build_frame()
    assert set(df["race_position"].dropna().unique()) <= {4, 5}


def test_udp_to_srt_wheel_order_and_axes():
    from telemetria_server.udp import structs

    tel = np.zeros(1, dtype=structs.CarTelemetryData_DT)[0]
    tel["m_tyresSurfaceTemperature"] = [10, 11, 20, 21]  # UDP order RL, RR, FL, FR
    row = cols.telemetry_row(tel)
    assert [row[f"tyre_temp_{i}"] for i in range(4)] == [20, 21, 10, 11]  # SRT order FL, FR, RL, RR

    mo = np.zeros(1, dtype=structs.CarMotionData_DT)[0]
    mo["m_gForceLateral"], mo["m_gForceLongitudinal"], mo["m_gForceVertical"] = 1500, -2000, 3000
    mo["m_worldPositionX"], mo["m_worldPositionY"], mo["m_worldPositionZ"] = 1.0, 2.0, 3.0
    m = cols.motion_row(mo)
    assert (m["gforce_X"], m["gforce_Y"], m["gforce_Z"]) == (2.0, 1.5, 3.0)
    assert (m["world_position_X"], m["world_position_Y"], m["world_position_Z"]) == (-1.0, 3.0, 2.0)

    ex = np.zeros(1, dtype=structs.CarMotionExData_DT)[0] if hasattr(structs, "CarMotionExData_DT") else None
    if ex is None:
        ex = np.zeros(1, dtype=structs.PacketMotionEXData_PAYLOAD_DT)[0]["m_carMotionEXData"]
    ex["m_localVelocityX"], ex["m_localVelocityY"], ex["m_localVelocityZ"] = -2.0, 0.5, 70.0
    e = cols.motion_ex_row(ex)
    assert (e["velocity_X"], e["velocity_Y"], e["velocity_Z"]) == (70.0, 2.0, -0.5)
