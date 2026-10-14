"""Setup reading (seam 1): raw SRT-convention channels -> the garage setup the game shows."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from telemetry.db import connect, get_session
from telemetry.garage import garage_from_raw, is_raw_setup, out_of_range, raw_asymmetry, to_garage
from telemetry.import_session import ingest_dataframe
from telemetry.loader import load_telemetry, setup_from_telemetry
from telemetry.setup_history import compute_setup_fingerprint, diff_setups, parse_setup_json
from telemetry.setup_reread import reread_library_setups
from telemetry.setup_tweaker import SETUP_PARAMS, display_value, normalize_setup

ROOT = Path(__file__).resolve().parent.parent
PARAM = {p.key: p for p in SETUP_PARAMS}
deg = np.pi / 180.0

# Miami garage as the game shows it (stored units: fractions, Pa; see display_scale)
MIAMI = {
    "wing_setup_0": 25, "wing_setup_1": 20,
    "camber_setup_0": -3.50, "camber_setup_1": -2.00,
    "toe_setup_0": 0.01, "toe_setup_1": 0.12,
    "susp_spring_setup_0": 38, "susp_spring_setup_1": 4,
    "arb_setup_0": 6, "arb_setup_1": 14,
    "susp_height_setup_0": 21, "susp_height_setup_1": 21, "susp_height_setup_2": 48, "susp_height_setup_3": 48,
    "diff_onThrottle_setup": 1.0, "diff_offThrottle_setup": 0.2,
    "brake_press_setup": 0.99, "brake_bias_setup": 0.56, "brake_engine_setup": 0.50, "ballast_setup": 6,
}


def raw_row(**over) -> dict[str, float]:
    """Synthetic SRT row (front-first wheels, radians, Pa) for the Miami garage."""
    row = {
        "wing_setup_0": 25, "wing_setup_1": 20,
        "diff_onThrottle_setup": 1.0, "diff_offThrottle_setup": 0.2,
        "camber_setup_0": -3.5 * deg, "camber_setup_1": -3.5 * deg, "camber_setup_2": -2.0 * deg, "camber_setup_3": -2.0 * deg,
        "toe_setup_0": 0.01 * deg, "toe_setup_1": 0.01 * deg, "toe_setup_2": 0.12 * deg, "toe_setup_3": 0.12 * deg,
        "susp_spring_setup_0": 38, "susp_spring_setup_1": 38, "susp_spring_setup_2": 4, "susp_spring_setup_3": 4,
        "arb_setup_0": 6, "arb_setup_1": 14,
        "susp_height_setup_0": 21, "susp_height_setup_1": 21, "susp_height_setup_2": 48, "susp_height_setup_3": 48,
        "brake_press_setup": 0.99, "brake_bias_setup": 0.56, "brake_engine_setup": 0.5, "ballast_setup": 6,
        "tyre_press_setup_0": 179264, "tyre_press_setup_1": 179264, "tyre_press_setup_2": 156511, "tyre_press_setup_3": 156511,
    }
    row.update(over)
    return row


def assert_miami(setup: dict) -> None:
    for key, want in MIAMI.items():
        assert setup[key] == pytest.approx(want, abs=1e-6), key
    assert display_value(PARAM["diff_onThrottle_setup"], setup["diff_onThrottle_setup"]) == pytest.approx(100)
    assert display_value(PARAM["diff_offThrottle_setup"], setup["diff_offThrottle_setup"]) == pytest.approx(20)
    assert display_value(PARAM["brake_engine_setup"], setup["brake_engine_setup"]) == pytest.approx(50)
    psi = [display_value(PARAM[f"tyre_press_setup_{i}"], setup[f"tyre_press_setup_{i}"]) for i in range(4)]
    assert psi == pytest.approx([26.0, 26.0, 22.7, 22.7], abs=0.05)


def test_synthetic_row_reads_front_and_rear_from_the_right_wheels():
    g = garage_from_raw(raw_row())
    assert_miami(g)
    assert out_of_range(g) == {}


def test_front_right_slot_never_leaks_into_rear():
    # FL/FR carry the front value, RL/RR the rear one; a reader using index 1 as rear would see -3.5 / 38
    g = garage_from_raw(raw_row())
    assert g["camber_setup_1"] == pytest.approx(-2.0) and g["susp_spring_setup_1"] == 4 and g["toe_setup_1"] == pytest.approx(0.12)


def test_out_of_range_values_are_surfaced_not_clipped():
    g = garage_from_raw(raw_row(camber_setup_0=-5.0 * deg, wing_setup_0=60))
    assert g["camber_setup_0"] == pytest.approx(-5.0) and g["wing_setup_0"] == 60
    assert normalize_setup(raw_row(camber_setup_0=-5.0 * deg))["camber_setup_0"] == pytest.approx(-5.0)
    flagged = out_of_range(g)
    assert set(flagged) == {"camber_setup_0", "wing_setup_0"}


def test_left_right_difference_is_reported_not_averaged():
    raw = raw_row(camber_setup_1=-3.2 * deg, susp_height_setup_3=50)
    g = garage_from_raw(raw)
    assert g["camber_setup_0"] == pytest.approx(-3.5)  # front = FL
    assert raw_asymmetry(raw) == {"camber_setup_0": (-3.5, -3.2), "susp_height_setup_2": (48.0, 50.0)}
    assert raw_asymmetry(raw_row()) == {}


def test_canonical_dict_is_not_converted_again():
    g = garage_from_raw(raw_row())
    assert not is_raw_setup(g) and is_raw_setup(raw_row())
    assert to_garage(g) == g
    assert normalize_setup(g) == normalize_setup(normalize_setup(g))
    assert compute_setup_fingerprint(g) == compute_setup_fingerprint(to_garage(g))
    # old front-only raw channels (compact parquet from before the rear slots were kept): radians detected, rear unknown
    old = {k: v for k, v in raw_row().items() if not k.endswith(("_2", "_3")) or k.startswith(("susp_h", "tyre_p"))}
    g_old = garage_from_raw(old)
    assert g_old["camber_setup_0"] == pytest.approx(-3.5) and "camber_setup_1" not in g_old


def test_equal_garages_give_equal_fingerprints_and_no_diff():
    a, b = garage_from_raw(raw_row()), garage_from_raw(raw_row(camber_setup_1=-3.5 * deg + 1e-7))
    assert compute_setup_fingerprint(a) == compute_setup_fingerprint(b)
    assert diff_setups(a, b) == []
    changed = garage_from_raw(raw_row(arb_setup_1=15))
    assert [d["key"] for d in diff_setups(a, changed)] == ["arb_setup_1"]


def test_stable_median_skips_reset_rows():
    import pandas as pd

    rows = [raw_row(lapNum=1) for _ in range(30)]
    rows += [raw_row(lapNum=2, wing_setup_0=0, wing_setup_1=0, arb_setup_0=0, arb_setup_1=0) for _ in range(30)]
    df = pd.DataFrame(rows).rename(columns={"lapNum": "lap"})
    assert_miami(setup_from_telemetry(df))
    assert_miami(setup_from_telemetry(df, 2))  # reset lap falls back to the nearest real garage


# --- real Miami exports (repo root, gitignored) ---------------------------------------------------

@pytest.mark.parametrize("name", ["Miami_FP_Ferrari.csv", "Miami_Q_Ferrari.csv", "Miami_RACE_Ferrari.csv"])
def test_real_miami_exports_read_the_in_game_garage(name):
    path = ROOT / name
    if not path.exists():
        pytest.skip(f"{name} not present")
    assert_miami(setup_from_telemetry(load_telemetry(path)))


# --- recorder parity --------------------------------------------------------------------------------

def test_recorder_setup_row_reads_back_as_garage_values():
    from telemetria_server.udp import srt_columns as cols

    names = ("m_frontWing", "m_rearWing", "m_onThrottle", "m_offThrottle", "m_frontCamber", "m_rearCamber",
             "m_frontToe", "m_rearToe", "m_frontSuspension", "m_rearSuspension", "m_frontAntiRollBar",
             "m_rearAntiRollBar", "m_frontSuspensionHeight", "m_rearSuspensionHeight", "m_brakePressure",
             "m_brakeBias", "m_engineBraking", "m_rearLeftTyrePressure", "m_rearRightTyrePressure",
             "m_frontLeftTyrePressure", "m_frontRightTyrePressure", "m_ballast", "m_fuelLoad")
    c = np.zeros(1, dtype=np.dtype([(n, "<f4") for n in names]))[0]
    for k, v in dict(m_frontWing=25, m_rearWing=20, m_onThrottle=100, m_offThrottle=20, m_frontCamber=-3.5, m_rearCamber=-2.0,
                     m_frontToe=0.01, m_rearToe=0.12, m_frontSuspension=38, m_rearSuspension=4, m_frontAntiRollBar=6,
                     m_rearAntiRollBar=14, m_frontSuspensionHeight=21, m_rearSuspensionHeight=48, m_brakePressure=99,
                     m_brakeBias=56, m_engineBraking=50, m_ballast=6, m_fuelLoad=20,
                     m_frontLeftTyrePressure=26.0, m_frontRightTyrePressure=26.0,
                     m_rearLeftTyrePressure=22.7, m_rearRightTyrePressure=22.7).items():
        c[k] = v
    g = garage_from_raw(cols.setup_row(c))
    assert_miami(g)
    assert raw_asymmetry(cols.setup_row(c)) == {}


def test_recorded_capture_reads_in_range_front_and_rear():
    from telemetria_server.udp.capture_file import iter_capture
    from telemetria_server.udp.recorder import SessionRecorder

    cap = ROOT / "data" / "udp_captures" / "20261009-222554.f1cap"
    if not cap.exists():
        pytest.skip("no local capture")
    r = SessionRecorder()
    for i, (t, d) in enumerate(iter_capture(cap)):
        if r.is_new_session(d) or i > 130_000:
            break
        r.feed(d, t)
    g = setup_from_telemetry(r.build_frame())
    assert g and out_of_range(g) == {}
    assert g["camber_setup_0"] < g["camber_setup_1"] < 0  # front more negative than rear


# --- library repair ----------------------------------------------------------------------------------

def _tmp_library_with_wrong_setup(tmp_root):
    import pandas as pd

    rng = np.random.default_rng(0)
    n = 4000
    dist = np.tile(np.linspace(0, 5000, 1000), 4)
    df = pd.DataFrame(
        {
            "lap": np.repeat([1, 2, 3, 4], 1000),
            "lap_distance": dist,
            "lap_time": np.tile(np.linspace(0, 90, 1000), 4),
            "speed": 200 + rng.normal(0, 5, n),
            "throttle": 0.8, "brake": 0.0, "gear": 5, "steering": 0.0, "rpm": 10000, "fuel": 50.0,
            "pos_x": dist, "pos_y": 0.0, "pos_z": 0.0, "trackLength": 5000.0,
            "track": "Miami", "car": "Ferrari",
            **{k: v for k, v in raw_row().items()},
        }
    )
    res = ingest_dataframe(df, source_name="repair_test", source_hash="b" * 64, original_size=1, app_root=tmp_root)
    return res.session_id


def test_library_repair_rereads_backs_up_and_runs_once(tmp_root):
    sid = _tmp_library_with_wrong_setup(tmp_root)
    wrong = {"camber_setup_0": -3.5, "camber_setup_1": -2.5, "susp_spring_setup_1": 38, "wing_setup_0": 25, "wing_setup_1": 20}
    with connect(tmp_root) as conn:
        conn.execute("UPDATE sessions SET setup_json = ?, setup_fingerprint = 'stale' WHERE id = ?", (json.dumps(wrong), sid))
        # a session without a telemetry file keeps whatever it has stored
        conn.execute(
            "INSERT INTO sessions (created_at, source_name, source_hash, telemetry_path, setup_json, setup_fingerprint) "
            "VALUES ('2026-01-01', 'nofile', 'c', 'data/sessions/missing.parquet', ?, 'keepfp')",
            (json.dumps(wrong),),
        )
        keep_id = conn.execute("SELECT id FROM sessions WHERE source_name = 'nofile'").fetchone()[0]
        # legacy: raw radians stored as the setup, telemetry without setup channels -> unit fix, rear unknown
        conn.execute(
            "INSERT INTO sessions (created_at, source_name, source_hash, telemetry_path, setup_json) "
            "VALUES ('2026-01-02', 'rawstored', 'd', 'data/sessions/missing.parquet', ?)",
            (json.dumps({"camber_setup_0": -0.0610865, "camber_setup_1": -0.0610865, "wing_setup_0": 50, "wing_setup_1": 18}),),
        )
        raw_id = conn.execute("SELECT id FROM sessions WHERE source_name = 'rawstored'").fetchone()[0]

    res = reread_library_setups(tmp_root)
    assert res["done"] and res["repaired"] == 2 and res["kept"] == 1
    fixed = parse_setup_json(get_session(sid, tmp_root)["setup_json"])
    assert_miami(fixed)
    assert get_session(sid, tmp_root)["setup_fingerprint"] == compute_setup_fingerprint(fixed) != "stale"
    kept = get_session(keep_id, tmp_root)
    assert parse_setup_json(kept["setup_json"]) == wrong and kept["setup_fingerprint"] == "keepfp"

    legacy = parse_setup_json(get_session(raw_id, tmp_root)["setup_json"])
    assert legacy["camber_setup_0"] == pytest.approx(-3.5, abs=0.01) and "camber_setup_1" not in legacy

    backup = Path(res["backup"])
    assert backup.parent == tmp_root / "data" / "backups" and backup.name.endswith("before-setup-reread")
    con = sqlite3.connect(str(backup / "telemetry.db"))
    try:
        assert json.loads(con.execute("SELECT setup_json FROM sessions WHERE id = ?", (sid,)).fetchone()[0]) == wrong
    finally:
        con.close()

    again = reread_library_setups(tmp_root)
    assert not again["done"] and again["backup"] is None
    assert len(list((tmp_root / "data" / "backups").iterdir())) == 1
    assert parse_setup_json(get_session(sid, tmp_root)["setup_json"]) == fixed
