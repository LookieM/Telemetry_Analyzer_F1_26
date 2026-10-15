"""Live duel scenarios: synthetic laps and commands in, asserts on view() / result() only."""

import json

import pytest

from telemetria_server.live.duel import Duel
from telemetria_server.live.engineer import EngineerError
from telemetria_server.live.lap_correction import Lap

BASE = {"wing_setup_0": 25.0, "wing_setup_1": 20.0, "diff_onThrottle_setup": 1.0, "arb_setup_0": 6.0,
        "brake_bias_setup": 0.56, "tyre_press_setup_0": 82000.0, "fuel_setup": 40.0}


def setup(**kw):
    return {**BASE, **kw}


SA, SB, SC = setup(wing_setup_0=25.0), setup(wing_setup_0=30.0), setup(wing_setup_0=35.0)


def make(n=2, names=None, **kw):
    d = Duel()
    args = dict(n=n, names=names, track="Miami", session_type="FP1", wet=False, now_s=1000.0, fuel_s_per_kg=0.05)
    args.update(kw)
    d.start(**args)
    return d


class Car:
    def __init__(self, d):
        self.d, self.n = d, 0

    def laps(self, s, times, **kw):
        for i, t in enumerate(times):
            self.n += 1
            args = dict(lap=self.n, lap_time_s=t, setup=dict(s), compound=18, tyre_set_idx=1, tyre_age_laps=2 + i)
            args.update(kw)
            self.d.on_lap(Lap(**args))


def by_key(d, k):
    return next(c for c in d.view()["contestants"] if c["key"] == k)


def test_start_refusals():
    with pytest.raises(EngineerError, match="practice"):
        make(session_type="Race")
    with pytest.raises(EngineerError, match="wet"):
        make(wet=True)
    with pytest.raises(EngineerError, match="2 or 3"):
        make(n=4)
    d = make()
    with pytest.raises(EngineerError, match="already"):
        d.start(2, None, "Miami", "FP1", False, 1.0)
    with pytest.raises(EngineerError):
        Duel().stop()


def test_instruction_and_names():
    d = make(3, ["Internet A", "", "  my Monza "])
    v = d.view()
    assert [c["label"] for c in v["contestants"]] == ["Internet A", "Setup B", "my Monza"]
    assert v["instruction"] == "Load Internet A in the garage and drive 4 laps"
    assert v["phase"] == "running" and v["next"] == "A"


def test_assignment_by_fingerprint_in_order():
    d, car = make(3), None
    car = Car(d)
    car.laps(SA, [90.0])
    assert by_key(d, "A")["assigned"] and not by_key(d, "B")["assigned"]
    car.laps(SB, [90.2])
    car.laps(SA, [90.1])
    assert by_key(d, "A")["counted"] == 2 and by_key(d, "B")["counted"] == 1
    assert d.view()["current"] == "A"


def test_fuel_and_compound_do_not_make_a_new_setup():
    d = make()
    car = Car(d)
    car.laps(SA, [90.0])
    car.laps(setup(fuel_setup=10.0, front_brake_bias=0.5, tyre_compound=3.0), [90.0])
    assert by_key(d, "A")["counted"] == 2 and not by_key(d, "B")["assigned"]


def test_pressure_only_difference_warns_and_counts_as_same():
    d = make()
    car = Car(d)
    car.laps(SA, [90.0])
    car.laps(setup(tyre_press_setup_0=84000.0), [90.0])
    v = d.view()
    assert by_key(d, "A")["counted"] == 2 and not by_key(d, "B")["assigned"]
    assert "tyre pressures" in v["detected"]["warning"]


def test_unknown_third_setup_is_not_counted():
    d = make(2)
    car = Car(d)
    car.laps(SA, [90.0])
    car.laps(SB, [90.0])
    car.laps(SC, [90.0])
    v = d.view()
    assert sum(c["counted"] for c in v["contestants"]) == 2
    assert "unknown setup" in v["detected"]["warning"]


def test_repeating_a_finished_setup_when_leaving_the_garage_warns():
    d = make()
    car = Car(d)
    car.laps(SA, [90.0] * 4)
    d.on_garage(True, 1100.0)
    d.on_garage(False, 1110.0, SA)
    w = d.view()["detected"]["warning"]
    assert "Setup A again" in w and "Setup B" in w


def test_leaving_the_garage_assigns_and_shows_on_car():
    d = make()
    d.on_garage(True, 1001.0)
    d.on_garage(False, 1010.0, SA)
    v = d.view()
    assert v["current"] == "A" and by_key(d, "A")["on_car"] and v["instruction"] == "Setup A: lap 1 of 4"


def test_lap_counting_min_target_max_and_rules():
    d = make()
    car = Car(d)
    car.laps(SA, [90.0] * 2)
    car.laps(SA, [95.0], valid=False)
    car.laps(SA, [92.0], in_lap=True)
    car.laps(SA, [92.0], out_lap=True)
    car.laps(SA, [92.0], pit=True)
    assert by_key(d, "A")["counted"] == 2
    car.laps(SA, [95.0])                                   # 5 s slower than the median: a mistake
    assert by_key(d, "A")["counted"] == 2
    car.laps(SA, [90.1, 90.2])
    assert by_key(d, "A")["counted"] == 4 and by_key(d, "A")["status"] == "done"
    car.laps(SA, [90.3, 90.4])
    assert by_key(d, "A")["counted"] == 5                  # max
    assert "already has 5" in d.view()["detected"]["warning"]
    car.laps(SA, [90.0], compound=17)                      # other compound: refused
    assert by_key(d, "A")["counted"] == 5 and "fit the" in d.view()["detected"]["warning"]
    car.laps(SB, [90.0], compound=17)
    assert by_key(d, "B")["counted"] == 0


def test_question_only_in_garage_after_all_contestants():
    d = make()
    car = Car(d)
    car.laps(SA, [90.0] * 4)
    d.on_garage(True, 1100.0)
    assert not d.view()["question"]["pending"]             # B not driven
    d.on_garage(False, 1110.0, SB)
    car.laps(SB, [90.0, 90.1])
    d.on_garage(True, 1200.0)
    assert not d.view()["question"]["pending"]             # B has only 2
    with pytest.raises(EngineerError, match="Not ready"):
        d.rank(["A", "B"])
    d.on_garage(False, 1210.0, SB)
    car.laps(SB, [90.2])
    assert not d.view()["question"]["pending"]             # on track
    d.on_garage(True, 1300.0)
    v = d.view()
    assert v["question"]["pending"] and v["question"]["keys"] == ["A", "B"]
    assert "rank the setups by feel" in v["instruction"]


def ready_duel(ta, tb, tc=None, wear=None):
    d = make(3 if tc else 2, ["Fast", "Slow", "Third"] if tc else None)
    car = Car(d)
    for s, times in ((SA, ta), (SB, tb), (SC, tc)):
        if times is None:
            continue
        for i, t in enumerate(times):
            car.laps(s, [t], tyre_age_laps=2 + i, wear_avg_pct=(wear or {}).get(s["wing_setup_0"], 0) * i + 2)
    d.on_garage(True, 2000.0)
    return d


def test_rank_wrong_order_and_wrong_phase():
    d = ready_duel([90.0] * 4, [91.0] * 4)
    with pytest.raises(EngineerError, match="exactly once"):
        d.rank(["A", "A"])
    with pytest.raises(EngineerError, match="exactly once"):
        d.rank(["A"])
    with pytest.raises(EngineerError, match="Nothing to confirm"):
        d.confirm("A")


def test_feel_ranking_then_ranking_by_stopwatch():
    d = ready_duel([90.0, 90.1, 89.9, 90.0], [91.0, 91.1, 90.9, 91.0])
    v = d.rank(["B", "A"], " B felt planted")
    r = v["ranking"]
    assert v["phase"] == "review" and r["winner"] == "A" and r["tie_break"] == "stopwatch" and r["proposed"] == "A"
    assert v["feel"] == {"order": ["B", "A"], "note": "B felt planted"}
    assert any("rated" in c and "you decide" in c for c in r["callouts"])      # feel and stopwatch disagree
    assert [x["rank"] for x in r["contestants"]] == [1, 2]


def test_tie_inside_noise_falls_to_feel():
    d = ready_duel([90.0, 90.2, 89.9, 90.1], [90.0, 90.2, 89.9, 90.1])
    r = d.rank(["B", "A"])["ranking"]
    assert r["tie_break"] == "feel" and r["winner"] == "B" and r["order"] == ["B", "A"]
    d = ready_duel([90.0, 90.2, 89.9, 90.1], [90.0, 90.2, 89.9, 90.1])
    r = d.rank(["A", "B"])["ranking"]
    assert r["winner"] == "A"


def test_fuel_correction_removes_the_lighter_car_advantage():
    d = make()
    car = Car(d)
    for i in range(4):                                     # A drove heavy, B light: raw B is 0.5 s faster per lap
        car.laps(SA, [90.5], fuel_start=40.0, fuel_end=39.0)
        car.laps(SB, [90.0], fuel_start=30.0, fuel_end=29.0)
    d.on_garage(True, 2000.0)
    r = d.rank(["A", "B"])["ranking"]
    a, b = r["contestants"][0], r["contestants"][1]
    assert abs(a["race_pace_s"] - b["race_pace_s"]) < 0.01      # 10 kg x 0.05 s/kg explains the whole raw gap


def test_three_contestants_and_wear_cost_and_confirm_result():
    wear = {25.0: 0.2, 30.0: 0.2, 35.0: 1.0}
    d = ready_duel([90.0, 90.1, 89.9, 90.0], [90.5, 90.6, 90.4, 90.5], [90.0, 90.1, 89.9, 90.0], wear)
    v = d.rank(["A", "B", "C"], None, plan_time=lambda w: 1000.0 + 20 * w, race_laps=20)
    r = v["ranking"]
    assert r["cost_source"] == "model" and r["winner"] == "A"
    c = next(x for x in r["contestants"] if x["key"] == "C")
    assert c["race_cost_s"] > 0 and c["wear_pct_per_lap"] == pytest.approx(1.0)
    v = d.confirm("A")
    assert v["phase"] == "done" and v["winner"] == "A"
    res = d.result()
    json.dumps(res)
    assert res["mode"] == "live" and res["confirmed"] and res["winner"] == "A" and res["winner_label"] == "Fast"
    assert res["winner_setup"]["wing_setup_0"] == 25.0 and res["winner_fingerprint"]
    assert [c["key"] for c in res["contestants"]] == ["A", "B", "C"] and res["ranking"]["order"][0] == "A"
    assert d.drain_feed()


def test_confirm_can_override_the_ranking():
    d = ready_duel([90.0, 90.1, 89.9, 90.0], [91.0, 91.1, 90.9, 91.0])
    d.rank(["A", "B"])
    with pytest.raises(EngineerError):
        d.confirm("Z")
    d.confirm("B")
    assert d.result()["winner"] == "B"


def test_stop_keeps_partial_result_without_winner():
    d = ready_duel([90.0, 90.1, 89.9, 90.0], [91.0, 91.1, 90.9, 91.0])
    v = d.stop()
    assert v["phase"] == "done" and v["stop_reason"] == "stopped" and v["winner"] is None
    res = d.result()
    assert not res["confirmed"] and res["winner"] is None and res["winner_setup"] is None
    assert res["ranking"] and res["ranking"]["winner"] == "A" and res["contestants"][0]["counted"] == 4
    assert d.stop()["phase"] == "done"                     # idempotent


def test_stop_with_too_little_data_has_no_ranking():
    d = make()
    Car(d).laps(SA, [90.0] * 2)
    d.stop()
    res = d.result()
    assert res["ranking"] is None and res["contestants"][0]["counted"] == 2


def test_skip_contestant_needs_two_left():
    d = make(3)
    car = Car(d)
    car.laps(SA, [90.0] * 4)
    car.laps(SB, [91.0] * 4)
    assert d.view()["next"] == "C"
    d.skip_contestant()
    v = d.view()
    assert by_key(d, "C")["skipped"] and v["question"]["keys"] == ["A", "B"]
    d.on_garage(True, 3000.0)
    assert d.view()["question"]["pending"]
    with pytest.raises(EngineerError):
        d.skip_contestant()
    assert d.rank(["B", "A"])["ranking"]["order"][0] == "A"


def test_laps_are_ignored_outside_running():
    d = make()
    Car(d).laps(SA, [90.0] * 4)
    d.stop()
    Car(d).laps(SB, [90.0] * 4)
    assert by_key(d, "B")["counted"] == 0


def test_tyre_hint_depends_on_spare_sets():
    d = make()
    fresh = {"compound": 18, "available": True, "fitted": False, "wear": 0}
    d.on_tyre_sets([{"compound": 18, "available": True, "fitted": True, "wear": 0}, fresh, dict(fresh)])
    assert "fit a fresh set for Setup A" in d.view()["tyre_hint"]
    d.on_tyre_sets([{"compound": 18, "available": True, "fitted": True, "wear": 0}, fresh])
    assert "Not enough spare" in d.view()["tyre_hint"]
    Car(d).laps(SA, [90.0])
    d.on_tyre_sets([])
    assert d.view()["tyre_hint"] is None


def test_balance_from_profiles_reaches_the_ranking():
    def prof(us):
        return {1: {"name": "T1", "speed_class": "slow", "time_s": 5.0,
                    "phases": {"entry": 1.0, "mid": 2.0, "exit": 2.0},
                    "understeer": {"entry": us, "mid": us + 1, "exit": us - 1}, "traction": 0.1}}
    d = make()
    car = Car(d)
    for _ in range(4):
        car.laps(SA, [90.0], profile=prof(2.0))
        car.laps(SB, [90.0], profile=prof(5.0))
    d.on_garage(True, 2000.0)
    r = d.rank(["B", "A"])["ranking"]
    a = next(x for x in r["contestants"] if x["key"] == "A")
    assert a["balance"]["entry"]["deg"] == pytest.approx(2.0) and r["tie_break"] == "balance" and r["winner"] == "A"
