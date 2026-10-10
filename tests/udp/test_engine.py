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
