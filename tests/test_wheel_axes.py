"""Wheel order and g-force axes (seam 1): export rows are front-first; the library is repaired once."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from conftest import DB_PATH, ROOT, copy_library_db, needs_library
from telemetry.channels import CAR_LAYOUT, WHEELS, resolve
from telemetry.db import connect, load_session_telemetry
from telemetry.loader import TYRE_LABELS, normalize_frame
from telemetry.tyres import TyreTargets
from telemetry.wheel_axes_fix import FLAG, repair_library_wheel_axes


def srt_rows(**over) -> pd.DataFrame:
    """Four samples of a synthetic SRT export: braking hard, then coasting."""
    n = 4
    cols = {
        "lap": [1] * n,
        "brake": [0.9, 0.9, 0.0, 0.0],
        "throttle": [0.0, 0.0, 0.5, 0.5],
        "gforce_X": [2.0, 2.0, -1.0, -1.0],  # SRT: minus longitudinal, so braking is positive
        "gforce_Y": [0.5, -1.5, 3.0, 3.0],  # lateral
        "gforce_Z": [1.0] * n,  # vertical
        **{f"wheel_slip_ratio_{i}": [0.0] * n for i in range(4)},
    }
    cols.update(over)
    return normalize_frame(pd.DataFrame(cols))


def test_one_front_first_constant_drives_the_others():
    assert WHEELS == ("FL", "FR", "RL", "RR") and TYRE_LABELS == WHEELS
    assert CAR_LAYOUT == (0, 1, 2, 3)
    assert WHEELS[CAR_LAYOUT[0]] == "FL" and WHEELS[CAR_LAYOUT[3]] == "RR"


def test_g_axes_follow_the_srt_convention():
    df = srt_rows()
    assert df["g_lat"].tolist() == [0.5, -1.5, 3.0, 3.0]
    assert df["g_long"].tolist() == [-2.0, -2.0, 1.0, 1.0]  # negative while braking, positive accelerating
    assert df["g_mag"].iloc[0] == pytest.approx(np.hypot(0.5, 2.0))  # planar: vertical is excluded
    assert resolve(df, "g_vert") == "gforce_Z"


def test_front_slip_while_braking_is_a_front_lockup():
    df = srt_rows(wheel_slip_ratio_0=[0.3, 0, 0, 0])  # FL
    assert df["lockup_front"].tolist() == [True, False, False, False]
    assert not df["lockup_rear"].any()
    assert df["lockup_risk"].tolist() == [True, False, False, False]


def test_rear_slip_while_braking_is_a_rear_lockup():
    df = srt_rows(wheel_slip_ratio_3=[0.3, 0.3, 0.3, 0.3])  # RR
    assert df["lockup_rear"].tolist() == [True, True, False, False]
    assert not df["lockup_front"].any()


def test_hot_pressure_target_picks_the_axle():
    t = TyreTargets(19, 80, 100, hot_front_psi=22.0, hot_rear_psi=23.0)
    assert [t.hot_target(i) for i in range(4)] == [22.0, 22.0, 23.0, 23.0]  # FL FR RL RR


# --------------------------------------------------------------------------- library repair


def _tmp_library(tmp_root: Path, ids: tuple[int, ...]) -> Path:
    """Tmp app root holding copies of the given real sessions (rows + parquets); the real data/ is never written."""
    copy_library_db(tmp_root / "data" / "telemetry.db")
    con = sqlite3.connect(str(tmp_root / "data" / "telemetry.db"))
    try:
        con.execute(f"DELETE FROM sessions WHERE id NOT IN ({','.join(str(i) for i in ids)})")
        con.commit()
        paths = [r[0] for r in con.execute("SELECT telemetry_path FROM sessions")]
    finally:
        con.close()
    for rel in paths:
        (tmp_root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, tmp_root / rel)
    return tmp_root


@needs_library
def test_repair_fixes_g_and_lockups_backs_up_and_runs_once(tmp_path):
    root = _tmp_library(tmp_path, (12, 45))
    before = {sid: load_session_telemetry(sid, root) for sid in (12, 45)}
    assert "gforce_X" not in before[12].columns and "gforce_X" in before[45].columns

    res = repair_library_wheel_axes(root)
    assert res["done"] and res["repaired"] == 2 and res["skipped"] == 0
    after = {sid: load_session_telemetry(sid, root) for sid in (12, 45)}

    # compact import: longitudinal recovered from the old g_lat, lateral missing
    b, a = before[12], after[12]
    np.testing.assert_allclose(a["g_long"], -b["g_lat"])
    assert a["g_lat"].isna().all() and a["g_mag"].isna().all()
    # full export: recomputed from the raw axes
    b, a = before[45], after[45]
    np.testing.assert_allclose(a["g_lat"], b["gforce_Y"], rtol=1e-5, atol=1e-6)
    np.testing.assert_allclose(a["g_long"], -b["gforce_X"], rtol=1e-5, atol=1e-6)
    np.testing.assert_allclose(a["g_mag"], np.hypot(b["gforce_Y"], b["gforce_X"]), rtol=1e-5, atol=1e-6)
    for sid in (12, 45):
        b, a = before[sid], after[sid]
        assert a["lockup_front"].tolist() == b["lockup_rear"].tolist()
        assert a["lockup_rear"].tolist() == b["lockup_front"].tolist()
        assert list(a.columns) == list(b.columns) and (a.dtypes == b.dtypes).all()
        assert a["tyre_temp_0"].equals(b["tyre_temp_0"])  # raw per-wheel arrays untouched

    backup = Path(res["backup"])
    assert backup.name.endswith("before-wheel-axes-fix") and (backup / "telemetry.db").exists()
    with connect(root) as conn:
        rels = [r[0] for r in conn.execute("SELECT telemetry_path FROM sessions")]
        assert conn.execute("SELECT 1 FROM library_meta WHERE key = ?", (FLAG,)).fetchone()
    for rel in rels:
        saved = pd.read_parquet(backup / rel)
        assert saved["g_lat"].equals(before[12 if "g_lat" in saved and "gforce_X" not in saved else 45]["g_lat"])
    assert not list((root / "data" / "sessions").glob("*.tmp"))

    again = repair_library_wheel_axes(root)
    assert not again["done"] and again["backup"] is None
    assert len(list((root / "data" / "backups").iterdir())) == 1
    for sid in (12, 45):
        assert load_session_telemetry(sid, root)["g_long"].equals(after[sid]["g_long"])
