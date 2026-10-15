from pathlib import Path

import pytest

from telemetria_server.live.engine import LiveEngine
from telemetria_server.live.state import LiveState
from telemetria_server.udp.capture_file import iter_capture

CAP = Path(__file__).resolve().parents[2] / "data" / "udp_captures" / "20261009-222554.f1cap"
pytestmark = pytest.mark.skipif(not CAP.exists(), reason="no local capture")


def test_engine_snapshots_over_a_real_race(tmp_path):
    (tmp_path / "data").mkdir()
    s, e = LiveState(), LiveEngine(LiveState(), tmp_path)
    e.s = s
    deltas, events, fuel_pl, last = [], [], None, None
    for i, (t, d) in enumerate(iter_capture(CAP)):
        s.feed(d, t)
        if i % 120:
            continue
        e.tick()
        events += e.pop_events()
        snap = e.snapshot()
        if snap is None:
            continue
        last = snap
        if snap["timing"]["delta_best"] is not None and snap["session"]["lap"] >= 3:
            deltas.append(snap["timing"]["delta_best"])
            assert snap["timing"]["delta_last"] is not None
        fuel_pl = snap["fuel"]["per_lap"] or fuel_pl
    assert last is not None and last["session"]["track"] == "Spa"
    assert last["engineer"] is None and e.engineer.phase == "idle"   # a race: the engineer stays out
    # once a clean reference lap exists the delta stays within a sane band
    deltas.sort(key=abs)
    assert deltas and abs(deltas[len(deltas) // 2]) < 10  # typical laps are close to the reference
    assert 0.5 < fuel_pl < 4
    kinds = {ev["kind"] for ev in events}
    assert {"pit_in", "pit_out"} & kinds or "sc" in kinds
    assert all(r["gap_s"] is not None for r in last["rivals"])


def test_damage_loss_is_measured_and_fuel_corrected():
    from telemetria_server.live.engine import LapRecord, damage_loss

    hist = [LapRecord(n, 90.0, True, False, False, 30 - n, 29 - n) for n in range(1, 5)]       # 90.0 s, 1 kg/lap
    hist.append(LapRecord(5, 95.0, True, False, False, 25, 24))                                # hit lap (excluded)
    hist += [LapRecord(n, 90.5, True, False, False, 30 - n, 29 - n) for n in range(6, 8)]      # +0.5 s raw
    hist.append(LapRecord(8, 110.0, True, True, False, 22, 21))                                # pit lap (excluded)
    loss = damage_loss(hist, 5, fuel_s_per_kg=0.1)
    # before laps 2-4 (fuel mid 27.5..25.5 -> 26.5), after laps 6-7 (fuel mid 23.5, 22.5 -> 23.0): 3.5 kg lighter
    assert loss["laps_before"] == 3 and loss["laps_after"] == 2
    assert abs(loss["loss_s"] - (0.5 + 0.35)) < 1e-9


def test_wing_advice_arithmetic():
    from telemetria_server.live.engine import wing_advice

    loss = {"loss_s": 0.8}
    assert wing_advice(5, loss, laps_left=20, pit_loss_s=22, wing_change_s=5, planned_stop_lap=None, lap_now=3)["call"] is None
    assert wing_advice(40, None, laps_left=20, pit_loss_s=22, wing_change_s=5, planned_stop_lap=None, lap_now=3)["call"] == "MEASURE"
    assert wing_advice(40, loss, laps_left=40, pit_loss_s=22, wing_change_s=5, planned_stop_lap=None, lap_now=3)["call"] == "BOX"   # 32 > 27
    assert wing_advice(40, loss, laps_left=20, pit_loss_s=22, wing_change_s=5, planned_stop_lap=None, lap_now=3)["call"] == "STAY"  # 16 < 27
    assert wing_advice(40, loss, laps_left=20, pit_loss_s=22, wing_change_s=5, planned_stop_lap=8, lap_now=3)["call"] == "AT_STOP"


def test_wing_advice_broken_wing_and_safety_car():
    from telemetria_server.live.engine import wing_advice

    kw = dict(laps_left=10, pit_loss_s=22, wing_change_s=5, planned_stop_lap=None, lap_now=6)
    assert wing_advice(100, None, **kw)["call"] == "BOX"            # broken: no need to measure
    assert wing_advice(30, None, sc=True, **kw)["call"] == "BOX"     # SC makes the stop cheap
    assert wing_advice(30, None, **kw)["call"] == "MEASURE"
    assert wing_advice(100, None, laps_left=1, pit_loss_s=22, wing_change_s=5, planned_stop_lap=None, lap_now=11)["call"] is None


def test_engine_hands_over_the_game_tyre_data_once_per_session(tmp_path):
    (tmp_path / "data").mkdir()
    s = LiveState()
    e = LiveEngine(s, tmp_path)
    payloads = []
    for i, (t, d) in enumerate(iter_capture(CAP)):
        s.feed(d, t)
        if i % 120 == 0:
            e.tick()
            if e.game_tyres_pending:
                payloads.append(e.game_tyres_pending)
                e.game_tyres_pending = None
        if i > 60_000:
            break
    assert len(payloads) == 1
    p = payloads[0]
    assert p["track"] == "Spa" and p["total_laps"] == 11
    roles = {x["actual"]: x["visual"] for x in p["sets"] if x["actual"] in (17, 18, 19)}
    assert roles == {17: 16, 18: 17, 19: 18}  # C4 soft, C3 medium, C2 hard


def test_engine_adapts_laps_into_the_engineer(tmp_path):
    """Replay a race but present it as FP1: laps reach the engineer with sectors, flags, fuel, age and the garage setup."""
    import numpy as np

    from telemetria_server.live.engineer import EngineerLap
    from telemetria_server.live.state import PID_SESSION

    (tmp_path / "data").mkdir()
    s = LiveState()
    e = LiveEngine(s, tmp_path)
    got: list[EngineerLap] = []
    orig = e.engineer.__class__.on_lap
    e.engineer.__class__.on_lap = lambda self, lap: (got.append(lap), orig(self, lap))[1]
    try:
        started = False
        for i, (t, d) in enumerate(iter_capture(CAP)):
            s.feed(d, t)
            if i % 120 or i < 3000:
                continue
            if s.get(PID_SESSION) is not None:
                sess = np.array([s.pk[PID_SESSION]])
                sess[0]["m_sessionType"], sess[0]["m_weather"] = 1, 0
                s.pk[PID_SESSION] = sess[0]
            e.tick()
            if not started and s.get(PID_SESSION) is not None:
                e.engineer_start("short")
                started = True
            if len(got) >= 3 or i > 250_000:
                break
    finally:
        e.engineer.__class__.on_lap = orig
    assert started and len(got) >= 3
    lap = got[1]
    assert 60 < lap.lap_time_s < 200 and lap.fuel_start > lap.fuel_end > 0 and lap.compound in (17, 18, 19)
    assert all(x is not None and x > 10 for x in (lap.s1, lap.s2, lap.s3)) and abs(sum(lap.sectors) - lap.lap_time_s) < 0.01
    assert lap.setup["wing_setup_0"] > 0 and lap.setup["camber_setup_0"] < -1       # garage degrees, not radians
    assert any(ev["kind"] == "engineer" for ev in e.pop_events())


def test_engine_attaches_a_corner_profile_from_the_recorder_to_each_full_lap(tmp_path):
    """Same replay, with the recorder wired in like the ingest does: full laps carry a profile (corners built from the
    live lap, kept in memory); a never-wired engine gives laps without one."""
    import numpy as np

    from telemetria_server.ingest import SessionManager
    from telemetria_server.live.engineer import EngineerLap
    from telemetria_server.live.state import PID_SESSION

    (tmp_path / "data").mkdir()
    s, mgr = LiveState(), SessionManager()
    e = LiveEngine(s, tmp_path)
    e.recorder_source = lambda: mgr.rec
    got: list[EngineerLap] = []
    orig = e.engineer.__class__.on_lap
    e.engineer.__class__.on_lap = lambda self, lap: (got.append(lap), orig(self, lap))[1]
    try:
        started = False
        for i, (t, d) in enumerate(iter_capture(CAP)):
            s.feed(d, t)
            mgr.feed(d, t)
            if i % 120 or i < 3000:
                continue
            if s.get(PID_SESSION) is not None:
                sess = np.array([s.pk[PID_SESSION]])
                sess[0]["m_sessionType"], sess[0]["m_weather"] = 1, 0
                s.pk[PID_SESSION] = sess[0]
            e.tick()
            if not started and s.get(PID_SESSION) is not None:
                e.engineer_start("short")
                started = True
            if len(got) >= 4 or i > 250_000:
                break
    finally:
        e.engineer.__class__.on_lap = orig
    full = [x for x in got if x.profile]
    assert len(full) >= 2
    prof = full[-1].profile
    assert len(prof) >= 10
    c = next(iter(prof.values()))
    assert 1 < c["time_s"] < 40 and abs(sum(c["phases"].values()) - c["time_s"]) < 0.5
    assert sum(x["understeer"]["mid"] is not None for x in prof.values()) >= len(prof) // 2
    total = sum(x["time_s"] for x in prof.values())
    assert 0.2 * full[-1].lap_time_s < total < full[-1].lap_time_s


def test_a_failing_recorder_never_breaks_the_engine(tmp_path):
    e = LiveEngine(LiveState(), tmp_path)
    assert e._lap_profile(3) is None                       # not wired
    e.recorder_source = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    assert e._lap_profile(3) is None
    e.recorder_source = lambda: None
    assert e._lap_profile(3) is None
