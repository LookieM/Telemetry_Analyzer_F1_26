"""Engineer scenarios: synthetic laps and answers in, asserts on view() / result() only."""

import json

import pytest

from telemetria_server.live.engineer import Engineer, EngineerError, EngineerLap

BASE = {"wing_setup_0": 25.0, "wing_setup_1": 20.0, "diff_onThrottle_setup": 1.0, "arb_setup_0": 6.0,
        "brake_bias_setup": 0.56}
KEY = "wing_setup_0"


def make(seed=1, program="short", **kw):
    e = Engineer(seed=seed)
    args = dict(program=program, baseline=dict(BASE), track="Miami", session_type="FP1", wet=False, now_s=1000.0,
                fuel_s_per_kg=0.05, deg_s_per_lap={}, minutes=None)
    args.update(kw)
    e.start(**args)
    return e


class Car:
    """Feeds laps to an engineer with running lap numbers."""

    def __init__(self, e, key=KEY):
        self.e, self.key, self.n = e, key, 0

    def laps(self, value, times, **kw):
        for i, t in enumerate(times):
            self.n += 1
            d = dict(lap=self.n, lap_time_s=t, setup={self.key: float(value)}, compound=18, tyre_set_idx=1,
                     tyre_age_laps=3 + i)
            d.update(kw)
            self.e.on_lap(EngineerLap(**d))


def vals(e):
    return {k: float(v) for k, v in e.view()["variants"].items()}


def drive(e, car, f, n=3, garage=True, **kw):
    """Run both variants of the current pair with lap time f(value), then back to the garage."""
    for v, value in vals(e).items():
        car.laps(value, [f(value)] * n, **kw)
    e.on_garage(garage, 1100.0)


def decide(e, car, f, **kw):
    drive(e, car, f, **kw)
    v = vals(e)
    best = "1" if f(v["1"]) < f(v["2"]) else "2"
    e.answer(best, "clear")
    e.confirm(best)
    e.on_garage(False, 1200.0)


def test_question_only_after_both_variants_and_garage():
    e, car = make(), None
    car = Car(e)
    v = vals(e)
    car.laps(v["1"], [90.0, 90.1, 89.9])
    e.on_garage(True)
    assert not e.view()["question"]["pending"]          # variant 2 not driven yet
    e.on_garage(False)
    car.laps(v["2"], [90.0, 90.0])
    assert not e.view()["question"]["pending"]          # not in the garage
    with pytest.raises(EngineerError):
        e.answer("1", "slight")
    e.on_garage(True)
    view = e.view()
    assert view["question"]["pending"] and "which felt better" in view["feed"][-1]["text"]
    assert view["run"]["counted"] == {"1": 3, "2": 2}


def test_random_order_is_seeded_and_hides_the_baseline():
    a, b = make(seed=7).view(), make(seed=7).view()
    assert a["variants"] == b["variants"]
    firsts = {make(seed=s).view()["variants"]["1"] for s in range(12)}
    assert firsts == {25, 28}
    assert sorted(a["variants"].values()) == [25, 28]
    assert "roles" not in json.dumps(a["variants"]) and a["last_result"] is None
    assert a["instruction"].startswith("Set Variant 1: Front wing")
    json.dumps(a)


def test_wrong_garage_value_warns_and_is_not_counted():
    e = make()
    car = Car(e)
    car.laps(31, [90.0, 90.0])
    view = e.view()
    assert view["run"]["counted"] == {"1": 0, "2": 0}
    assert view["detected"]["variant"] is None and "Front wing is 31" in view["detected"]["warning"]
    assert any("not counted" in f["text"] for f in view["feed"])
    car.laps(vals(e)["1"], [90.0])
    assert e.view()["detected"] == {"variant": "1", "warning": None}


def test_only_representative_laps_count():
    e = make()
    car = Car(e)
    one = vals(e)["1"]
    car.laps(one, [90.0, 90.1, 93.5])                       # third is 3.4 s off the median
    car.laps(one, [90.0], in_lap=True)
    car.laps(one, [90.0], out_lap=True)
    car.laps(one, [90.0], pit=True)
    car.laps(one, [89.0], valid=False)
    assert e.view()["run"]["counted"]["1"] == 2
    assert any("invalid" in f["text"] for f in e.view()["feed"])


def _label_of(e, value):
    return next(k for k, v in vals(e).items() if v == value)


def test_fuel_correction_flips_a_raw_verdict():
    e = make()
    car = Car(e)
    a, b = _label_of(e, 25.0), _label_of(e, 28.0)       # 25 = baseline "A", 28 = change "B"
    car.laps(vals(e)[a], [90.0] * 3, fuel_start=56.0, fuel_end=54.0)
    car.laps(vals(e)[b], [89.6] * 3, fuel_start=36.0, fuel_end=34.0)  # raw faster, but 20 kg lighter
    e.on_garage(True)
    e.answer(b, "slight")
    r = e.view()["last_result"]
    assert r["stopwatch_winner"] == a and r["measurable"]
    assert r["delta_s"] == pytest.approx((89.6 + 0.05 * 10) - (90.0 - 0.05 * 10) if b == "2" else -((89.6 + 0.5) - (89.5)), abs=1e-3)
    assert r["agreement"] == "disagree" and "stopwatch says" in r["agreement_text"]
    assert r["roles"][a] == "baseline" and r["roles"][b] == "change"


def test_tyre_age_correction_uses_the_compound_model():
    e = make(deg_s_per_lap={18: 0.1})
    car = Car(e)
    a, b = _label_of(e, 25.0), _label_of(e, 28.0)
    car.laps(vals(e)[a], [90.2] * 3, tyre_age_laps=2)
    car.laps(vals(e)[b], [90.3] * 3, tyre_age_laps=8)         # raw slower, but 6 laps older
    e.on_garage(True)
    e.answer(b, "clear")
    r = e.view()["last_result"]
    assert r["deg_source"] == "compound" and r["stopwatch_winner"] == b


def test_deg_is_fitted_from_the_pairs_own_laps_when_possible():
    e = make(deg_s_per_lap={18: 0.5})
    car = Car(e)
    one, two = vals(e)["1"], vals(e)["2"]
    car.laps(one, [90.0, 90.1], tyre_age_laps=1)
    car.laps(one, [90.2], tyre_age_laps=3)
    car.laps(two, [90.3, 90.4], tyre_age_laps=4)
    e.on_garage(True)
    e.answer("1", "slight")
    assert e.view()["last_result"]["deg_source"] == "fitted"


def test_below_noise_reads_as_no_measurable_difference():
    e = make()
    car = Car(e)
    one, two = vals(e)["1"], vals(e)["2"]
    car.laps(one, [90.00, 90.05, 89.95])
    car.laps(two, [90.02, 90.03, 90.01])
    e.on_garage(True)
    e.answer("1", "clear")
    r = e.view()["last_result"]
    assert not r["measurable"] and r["confidence"] == "none" and r["stopwatch_winner"] is None
    assert "No measurable difference" in r["text"]
    assert r["agreement"] == "disagree" and "cannot separate" in r["agreement_text"]


def test_disagreement_names_the_sectors_largest_first():
    e = make()
    car = Car(e)
    one, two = vals(e)["1"], vals(e)["2"]
    car.laps(one, [90.0] * 3, s1=30.0, s2=30.0, s3=30.0)
    car.laps(two, [90.4] * 3, s1=30.0, s2=30.1, s3=30.3)       # 2 is slower, mostly sector 3
    e.on_garage(True)
    e.answer("2", "clear", tags=["exit_slow", "traction"], note="more rotation")
    r = e.view()["last_result"]
    assert [s["sector"] for s in r["sectors"]][0] == 3
    assert r["agreement"] == "disagree"
    assert r["agreement_text"].index("S3") < r["agreement_text"].index("S2")
    assert r["your_answer"]["tags"] == ["exit_slow", "traction"] and r["your_answer"]["note"] == "more rotation"


def test_answer_validation():
    e = make()
    car = Car(e)
    drive(e, car, lambda v: 90.0)
    for bad in (dict(verdict="3"), dict(verdict="1", strength="huge"), dict(verdict="1", tags=["a"]),
                dict(verdict="1", tags=["kerbs"] * 2), dict(verdict="1", tags=["kerbs", "traction", "entry_slow", "mid_slow"])):
        with pytest.raises(EngineerError):
            e.answer(**{"strength": "slight", **bad})
    with pytest.raises(EngineerError):
        e.confirm("1")


def test_halving_until_the_smallest_step_settles_the_parameter():
    e = make()
    car = Car(e)
    f = lambda x: 90.0 - 0.2 * x                      # more wing is always faster
    assert sorted(vals(e).values()) == [25, 28]
    decide(e, car, f)
    assert sorted(vals(e).values()) == [28, 30]
    decide(e, car, f)
    assert sorted(vals(e).values()) == [30, 31]
    decide(e, car, f)
    v = e.view()
    assert [h["outcome"] for h in v["history"]] == ["changed"] * 3
    assert v["settled"][KEY] == {"label": "Front wing", "value": 31, "new": True}
    assert v["phase"] == "quali"                       # short program: one parameter
    assert e.result()["settled"] == {KEY: 31.0}


def test_two_same_answers_settle_and_keep_the_baseline():
    e = make()
    car = Car(e)
    for expected in ([25, 28], [25, 27]):
        assert sorted(vals(e).values()) == expected
        drive(e, car, lambda x: 90.0)
        e.answer("same", "slight")
        e.on_garage(False)
    v = e.view()
    assert v["settled"][KEY]["value"] == 25 and v["phase"] == "quali"
    assert [h["outcome"] for h in v["history"]] == ["same", "same"]


def test_range_limit_flips_the_direction():
    e = make(baseline={**BASE, KEY: 49.0})
    assert sorted(vals(e).values()) == [46, 49]
    low = make(baseline={**BASE, KEY: 0.0})
    assert sorted(vals(low).values()) == [0, 3]


def test_brake_bias_and_diff_use_display_percent():
    e = make(settled={"wing_setup_0": 25.0, "wing_setup_1": 20.0, "diff_onThrottle_setup": 1.0, "arb_setup_0": 6.0})
    v = e.view()
    assert v["param"]["label"] == "Brake bias" and v["param"]["unit"] == "%"
    assert sorted(v["variants"].values()) == [56, 58]


def test_settled_params_are_skipped_and_full_program_tests_three():
    e = make(program="full", settled={"wing_setup_0": 30.0})
    v = e.view()
    assert v["param"]["label"] == "Rear wing" and v["param"]["of"] == 3
    assert v["settled"][KEY]["value"] == 30 and not v["settled"][KEY]["new"]
    assert any("Settled earlier" in f["text"] for f in v["feed"])


def test_skip_moves_to_the_next_parameter():
    e = make(program="full")
    e.skip()
    v = e.view()
    assert v["param"]["label"] == "Rear wing" and v["history"][0]["outcome"] == "skipped"
    e2 = make()
    e2.skip()
    assert e2.view()["phase"] == "quali"


def test_time_budget_moves_on_to_quali_then_long_run_then_done():
    e = make(minutes=10)
    assert e.view()["budget"] == {"total_s": 600.0, "left_s": 600.0}
    e.on_tick(1300.0)
    assert e.view()["phase"] == "balance"
    e.on_tick(1370.0)                                    # 230 s left <= 40%
    v = e.view()
    assert v["phase"] == "quali" and any("Ending balance, quali check next" in f["text"] for f in v["feed"])
    e.on_tick(1460.0)                                    # 140 s left <= 25%
    assert e.view()["phase"] == "long_run"
    assert "Long run" in e.view()["instruction"]
    e.on_tick(1700.0)
    assert e.view()["phase"] == "done" and e.view()["budget"]["left_s"] == 0


def test_budget_is_capped_by_the_session_time_left():
    e = make(minutes=50, session_left_s=300)
    assert e.view()["budget"]["total_s"] == 300.0
    e.on_tick(1100.0, session_left_s=100)                # 100 s left of 300 -> quali already
    assert e.view()["phase"] == "quali"


def test_a_pending_question_defers_the_phase_change():
    e = make(minutes=10)
    car = Car(e)
    drive(e, car, lambda x: 90.0)
    e.on_tick(1500.0)
    assert e.view()["phase"] == "balance" and e.view()["question"]["pending"]
    e.answer("same", "slight")
    assert e.view()["phase"] == "quali"                  # moves on as soon as the question is resolved


def _quali_laps(e, car, f):
    for v, text in e.view()["variant_text"].items():
        car.laps(float(text.split()[-1]), [f(float(text.split()[-1]))] * 2)
    e.on_garage(True)


def test_parc_ferme_proposes_reverting_a_change_that_hurts():
    e = make()
    car = Car(e)
    drive(e, car, lambda x: 90.0 + (0.5 if x == 28 else 0.0))
    v = vals(e)
    slow = "1" if v["1"] == 28 else "2"
    e.answer(slow, "clear")                                # feel says the change is better, clock says no
    e.confirm(slow)
    e.on_garage(False)
    e.next_phase()
    v = e.view()
    assert v["phase"] == "quali" and "Quali check" in v["instruction"]
    _quali_laps(e, car, lambda x: 90.0 + (0.1 if x == 28 else 0.0))
    v = e.view()
    rp = v["revert_proposal"]
    assert v["phase"] == "quali" and rp["label"] == "Front wing" and rp["combined_s"] > 0 and rp["to"] == 25
    e.revert(True)
    assert e.view()["phase"] == "long_run" and e.view()["revert_proposal"] is None
    r = e.result()
    assert r["final"][KEY] == 25.0 and r["baseline"][KEY] == 25.0 and r["reverted"][0]["to"] == 25
    assert r["quali"]["delta_s"] == pytest.approx(0.1, abs=1e-6)


def test_parc_ferme_keeps_a_change_that_helps():
    e = make()
    car = Car(e)
    decide(e, car, lambda x: 90.0 - 0.3 * x)
    e.next_phase()
    _quali_laps(e, car, lambda x: 90.0 - 0.3 * x)
    v = e.view()
    assert v["phase"] == "long_run" and v["revert_proposal"] is None
    assert e.result()["final"][KEY] == 28.0


def test_quali_check_without_changes_is_just_two_reference_laps():
    e = make()
    e.next_phase()
    v = e.view()
    assert v["phase"] == "quali" and v["variants"] is None and "nothing changed" in v["feed"][-1]["text"]
    car = Car(e)
    car.laps(25.0, [90.0, 90.1])
    e.on_garage(True)
    assert e.view()["phase"] == "long_run"


def test_long_run_reports_pace_and_wear_then_finishes():
    e = make()
    car = Car(e)
    e.next_phase()
    e.next_phase()
    assert e.view()["phase"] == "long_run"
    for i in range(10):
        car.laps(25.0, [90.0 + 0.1 * i], tyre_age_laps=i, wear_max_pct=5.0 * i + 4,
                 fuel_start=50.0 - i, fuel_end=49.0 - i)
    v = e.view()
    assert v["phase"] == "done"
    lr = v["long_run"]
    assert len(lr["laps"]) == 10 and lr["wear_pct_per_lap"] == pytest.approx(5.0)
    assert lr["label"] == "Medium" or lr["label"]
    assert lr["pace_deg_s_per_lap"] == pytest.approx(0.1 + 0.05, abs=1e-6)   # raw 0.1 + fuel burn 0.05 s/kg
    assert e.result()["long_run"]["wear_pct_per_lap"] == pytest.approx(5.0)


def test_fresh_set_hint_depends_on_spare_sets():
    spare = [{"compound": 18, "available": True, "fitted": i == 0, "wear": 0, "life": 20} for i in range(4)]
    soft = [{"compound": 17, "available": True, "fitted": False, "wear": 0, "life": 20}]
    e = Engineer(seed=1)
    e.on_tyre_sets(spare + soft)
    e.start("short", dict(BASE), "Miami", "FP1", False, 0.0, deg_s_per_lap={})
    assert "fresh set" in e.view()["tyre_hint"] and "Spare" in e.view()["tyre_hint"]
    e2 = Engineer(seed=1)
    e2.on_tyre_sets(spare[:2] + soft)
    e2.start("short", dict(BASE), "Miami", "FP1", False, 0.0)
    assert "No spare" in e2.view()["tyre_hint"]


def test_refuses_outside_practice_and_in_the_wet():
    for st in ("Race", "Quali", "Test", ""):
        with pytest.raises(EngineerError, match="practice"):
            make(session_type=st)
    with pytest.raises(EngineerError, match="wet"):
        make(wet=True)
    with pytest.raises(EngineerError):
        make(program="medium")
    for st in ("FP1", "FP2", "FP3"):
        assert make(session_type=st).view()["phase"] == "balance"


def test_stop_ends_the_program_with_what_was_decided():
    e = make()
    car = Car(e)
    decide(e, car, lambda x: 90.0 - 0.3 * x)
    e.stop()
    v = e.view()
    assert v["phase"] == "done"
    r = e.result()
    assert r["stop_reason"] == "stopped" and r["pairs"][0]["outcome"] == "changed" and r["final"][KEY] == 28.0
    with pytest.raises(EngineerError):
        Engineer().stop()
    assert e.drain_feed() and e.drain_feed() == []


def test_idle_engineer_has_a_quiet_view():
    e = Engineer()
    v = e.view()
    assert v["phase"] == "idle" and v["variants"] is None
    e.on_lap(EngineerLap(lap=1, lap_time_s=90.0))      # ignored
    with pytest.raises(EngineerError):
        e.next_phase()


def test_baseline_offer_lists_what_changed_once_done():
    e = make()
    car = Car(e)
    assert e.view()["baseline_offer"] is None            # not done yet
    decide(e, car, lambda x: 90.0 - 0.3 * x)
    e.stop()
    offer = e.view()["baseline_offer"]
    assert offer["final"][KEY] == 28.0 and offer["final"]["wing_setup_1"] == 20.0
    assert offer["changed"] == [{"key": KEY, "label": "Front wing", "from": 25, "to": 28}]
    json.dumps(offer)


def test_baseline_offer_is_null_when_nothing_changed():
    e = make()
    e.stop()
    v = e.view()
    assert v["phase"] == "done" and v["baseline_offer"] is None
