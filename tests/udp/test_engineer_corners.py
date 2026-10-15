"""Engineer corner / phase A/B: synthetic laps with synthetic corner profiles in, result shapes out."""

import json

from telemetria_server.live.engineer import Engineer
from telemetry import engineer_log

from test_engineer import Car, make, vals


def prof(entry=1.0, mid=0.5, exit_=1.0, us=(2.0, 3.0, 0.2), traction=0.05, speed="slow", name="T4", extra=True):
    """Two-corner profile: T4 (the one under test) and a quiet T9."""
    out = {4: {"name": name, "speed_class": speed, "time_s": entry + mid + exit_,
               "phases": {"entry": entry, "mid": mid, "exit": exit_},
               "understeer": dict(zip(("entry", "mid", "exit"), us)), "traction": traction}}
    if extra:
        out[9] = {"name": "T9", "speed_class": "fast", "time_s": 2.0, "phases": {"entry": 0.7, "mid": 0.6, "exit": 0.7},
                  "understeer": {"entry": 2.0, "mid": 3.0, "exit": 0.2}, "traction": 0.04}
    return out


def test_top_corner_rows_and_tag_check_agree_with_the_stopwatch():
    e = make()
    car = Car(e)
    v = vals(e)
    car.laps(v["1"], [90.0] * 3, profile=prof(exit_=1.0, traction=0.08))
    car.laps(v["2"], [89.9] * 3, profile=prof(exit_=0.92, traction=0.05, us=(2.0, 3.0, 0.6)))
    e.on_garage(True)
    e.answer("2", "clear", tags=["exit_slow", "exit_fast", "kerbs"])
    r = e.view()["last_result"]
    top = r["corners"][0]
    assert (top["corner"], top["name"], top["phase"]) == (4, "T4", "exit")
    assert abs(top["delta_s"] + 0.08) < 1e-6 and abs(top["understeer_delta_deg"] - 0.4) < 1e-6
    assert abs(top["traction_delta"] + 0.03) < 1e-6
    assert len(r["corners"]) <= 5
    checks = {c["tag"]: c for c in r["tag_check"]}
    assert set(checks) == {"exit_slow", "exit_fast"}          # kerbs cannot be judged
    assert checks["exit_slow"]["agrees"] is True and checks["exit_slow"]["delta_s"] < -0.07
    assert checks["exit_fast"]["agrees"] is None and "no measurable" in checks["exit_fast"]["text"]


def test_traction_tag_uses_the_exit_rear_slip_difference():
    e = make()
    car = Car(e)
    v = vals(e)
    car.laps(v["1"], [90.0] * 3, profile=prof(traction=0.08))
    car.laps(v["2"], [90.0] * 3, profile=prof(traction=0.05))
    e.on_garage(True)
    e.answer("2", "slight", tags=["traction"])
    assert e.view()["last_result"]["tag_check"][0]["agrees"] is True


def test_tag_check_disagrees_when_the_variant_you_prefer_is_slower_there():
    e = make()
    car = Car(e)
    v = vals(e)
    car.laps(v["1"], [90.0] * 3, profile=prof(entry=1.0))
    car.laps(v["2"], [90.0] * 3, profile=prof(entry=1.1))
    e.on_garage(True)
    e.answer("2", "slight", tags=["entry_slow", "braking_stability"])
    checks = e.view()["last_result"]["tag_check"]
    assert [c["agrees"] for c in checks] == [False, False] and checks[0]["delta_s"] > 0.09
    assert "disagrees" in checks[0]["text"]


def test_same_verdict_has_no_agreement_and_corners_still_show():
    e = make()
    car = Car(e)
    v = vals(e)
    car.laps(v["1"], [90.0] * 3, profile=prof(mid=0.5))
    car.laps(v["2"], [90.0] * 3, profile=prof(mid=0.4))
    e.on_garage(True)
    e.answer("same", "slight", tags=["mid_slow"])
    row = e.view()["history"][-1]
    assert row["tag_check"][0]["agrees"] is None and row["corners"][0]["phase"] == "mid"


def test_corrections_are_spread_over_the_lap_by_corner_share():
    e = make()
    car = Car(e)
    v = vals(e)
    # variant 2 laps are one second slower in raw time only because the tyres are 10 laps older: same corners
    car.laps(v["1"], [90.0] * 3, profile=prof(), tyre_age_laps=3)
    car.laps(v["2"], [91.0] * 3, profile=prof(), tyre_age_laps=13)
    e.on_garage(True)
    e.answer("1", "slight")
    r = e.view()["last_result"]
    # the corrected lap delta is far smaller than +1 s, so the corner differences (profiles equal, scaled) stay tiny
    assert all(abs(c["delta_s"]) < 0.06 for c in r["corners"]) and r["corners"]


def test_missing_profiles_fall_back_to_sectors_only():
    e = make()
    car = Car(e)
    v = vals(e)
    car.laps(v["1"], [90.0] * 3)
    car.laps(v["2"], [90.0] * 2, profile=prof())
    car.laps(v["2"], [90.0], profile=None)
    e.on_garage(True)
    e.answer("2", "slight", tags=["exit_slow"])
    r = e.view()["last_result"]
    assert r["corners"] == [] and r["tag_check"] == [] and r["sectors"] is not None


def test_only_one_profile_in_a_variant_is_not_enough():
    e = make()
    car = Car(e)
    v = vals(e)
    car.laps(v["1"], [90.0] * 3, profile=prof())
    car.laps(v["2"], [90.0] * 3)
    car.laps(v["2"], [90.0], profile=prof())
    e.on_garage(True)
    e.answer("2", "slight", tags=["exit_slow"])
    assert e.view()["last_result"]["corners"] == []


def test_corners_and_tag_check_are_persisted_with_the_test(tmp_root):
    e = make()
    car = Car(e)
    v = vals(e)
    car.laps(v["1"], [90.0] * 3, profile=prof(exit_=1.0))
    car.laps(v["2"], [89.9] * 3, profile=prof(exit_=0.9))
    e.on_garage(True)
    e.answer("2", "clear", tags=["exit_slow"])
    e.confirm("2")
    result = json.loads(json.dumps(e.result()))
    row = result["pairs"][0]
    assert row["corners"][0]["phase"] == "exit" and row["tag_check"][0]["agrees"] is True
    engineer_log.save_test(e.result(), tmp_root)
    saved = engineer_log.list_tests("Miami", tmp_root)[-1]["result"]["pairs"][0]
    assert saved["corners"] == row["corners"] and saved["tag_check"] == row["tag_check"]
