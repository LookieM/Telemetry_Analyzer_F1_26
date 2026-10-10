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
        if snap["timing"]["delta"] is not None and snap["session"]["lap"] >= 3:
            deltas.append(snap["timing"]["delta"])
        fuel_pl = snap["fuel"]["per_lap"] or fuel_pl
    assert last is not None and last["session"]["track"] == "Spa"
    # once a clean reference lap exists the delta stays within a sane band
    deltas.sort(key=abs)
    assert deltas and abs(deltas[len(deltas) // 2]) < 10  # typical laps are close to the reference
    assert 0.5 < fuel_pl < 4
    kinds = {ev["kind"] for ev in events}
    assert {"pit_in", "pit_out"} & kinds or "sc" in kinds
    assert all(r["gap_s"] is not None for r in last["rivals"])
