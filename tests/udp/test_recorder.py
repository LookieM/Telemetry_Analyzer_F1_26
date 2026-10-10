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
