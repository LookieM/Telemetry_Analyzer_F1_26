"""Strategy optimiser, pit windows, in-race calls and the post-race review."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from conftest import ROOT, needs_library, session_by_source
from telemetry.strategy import CompoundSpec, RaceParams, _Costs, _plan_cost, lap_times, optimise, race_calls


def _specs(deg_s=0.30, deg_m=0.18, deg_h=0.10, wear=(6.0, 4.0, 2.5)):
    return [
        CompoundSpec(18, "S", "#f00", -0.5, deg_s, wear[0], 0.3),
        CompoundSpec(19, "M", "#ff0", 0.0, deg_m, wear[1], 0.3),
        CompoundSpec(20, "H", "#888", 0.4, deg_h, wear[2], 0.4),
    ]


def _brute_force(specs, params):
    costs = _Costs(specs, params)
    best = (float("inf"), None)
    R = params.laps
    for n in range(1, params.max_stops + 2):
        for combo in itertools.product(costs.specs, repeat=n):
            if not costs.valid(frozenset(combo)):
                continue
            for cuts in itertools.combinations(range(1, R), n - 1):
                lens = np.diff([0, *cuts, R])
                t = _plan_cost(combo, tuple(int(x) for x in lens), costs)
                if t < best[0]:
                    best = (t, combo)
    return best[0]


def test_dynamic_programme_matches_brute_force():
    params = RaceParams(laps=14, pit_loss_s=8.0, base_pace_s=90.0, max_stops=2, wear_limit_pct=40.0)
    specs = _specs(wear=(6.0, 4.0, 2.5))
    plans = optimise(specs, params)
    assert plans[0].race_time == pytest.approx(_brute_force(specs, params), abs=1e-6)


def test_no_degradation_and_two_compound_rule_means_one_stop():
    params = RaceParams(laps=30, pit_loss_s=22.0, base_pace_s=90.0)
    plans = optimise(_specs(0.0, 0.0, 0.0, wear=(None, None, None)), params)
    assert plans[0].stops == 1


def test_heavy_degradation_buys_extra_stops():
    params = RaceParams(laps=40, pit_loss_s=18.0, base_pace_s=90.0)
    plans = optimise(_specs(0.9, 0.7, 0.5, wear=(3.0, 2.5, 2.0)), params)
    assert plans[0].stops >= 2


def test_stints_respect_the_wear_limit_and_lap_times_add_up():
    params = RaceParams(laps=30, pit_loss_s=22.0, base_pace_s=90.0, wear_limit_pct=60.0)
    specs = _specs(wear=(10.0, 6.0, 4.0))  # max 6 / 10 / 15 laps
    plan = optimise(specs, params)[0]
    caps = {18: 6, 19: 10, 20: 15}
    assert all(n <= caps[c] for c, n in zip(plan.compounds, plan.stints))
    assert sum(plan.stints) == 30
    assert float(np.sum(lap_times(plan, specs, params))) == pytest.approx(plan.race_time, abs=1e-6)
    for (lo, hi), lap in zip(plan.windows, plan.stop_laps):
        assert lo <= lap <= hi


def test_a_safety_car_makes_boxing_cheaper_on_every_lap():
    params = RaceParams(laps=30, pit_loss_s=22.0, base_pace_s=90.0)
    specs = _specs()
    calls = race_calls(optimise(specs, params)[0], specs, params)
    green = calls["Green: box now vs stay (s)"].astype(float)
    sc = calls["SC: box now vs stay (s)"].astype(float)
    finite = np.isfinite(green) & np.isfinite(sc)
    assert (sc[finite] < green[finite]).all()
    assert (calls["SC call"] == "BOX").any()


@needs_library
def test_review_of_the_bahrain_race():
    from telemetry.strategy import default_params, review_race, specs_from_model
    from telemetry.tyres import session_frames, track_compound_model

    sid = session_by_source("bahrain_race.csv")["id"]
    _, _, summary = session_frames(sid, ROOT)
    model = track_compound_model("Bahrain", "dry", ROOT)
    review = review_race(summary, specs_from_model(model), default_params(model, "Bahrain"))
    assert review is not None
    assert review.actual.compounds == (19, 19, 20) and review.actual.stints == (8, 9, 12)
    assert review.strategy_cost_s >= 0  # the optimum can never be slower than the plan that was run


@needs_library
def test_review_counts_laps_the_export_skipped():
    from telemetry.strategy import actual_plan, default_params, review_race, specs_from_model
    from telemetry.tyres import session_frames, track_compound_model

    try:
        sid = session_by_source("Zandvoort_Race.csv")["id"]
    except BaseException:
        pytest.skip("Zandvoort race not in this library")
    _, _, summary = session_frames(sid, ROOT)
    plan = actual_plan(summary)
    assert sum(plan.stints) == 36 and plan.stints[0] == 13  # laps 11-12 missing but still raced
    model = track_compound_model("Zandvoort", "dry", ROOT)
    review = review_race(summary, specs_from_model(model), default_params(model, "Zandvoort"))
    assert review is not None and review.missing_laps == [11, 12] and review.actual_time is None
    assert review.execution_s is not None


def test_plan_from_state_agrees_with_race_calls_and_window():
    from telemetry.strategy import plan_from_state

    params = RaceParams(laps=30, pit_loss_s=22.0, base_pace_s=90.0, wear_limit_pct=60.0)
    specs = _specs(0.6, 0.45, 0.3, wear=(8.0, 5.0, 3.5))
    plan = optimise(specs, params)[0]
    calls = race_calls(plan, specs, params)
    stop = plan.stop_laps[0]
    row = calls[calls["Lap"] == stop].iloc[0]
    st = plan_from_state(specs, params, lap=stop, compound=plan.compounds[0], age=stop, used={plan.compounds[0]})
    assert st["box_now_s"] - st["stay_out_s"] == pytest.approx(row["Green: box now vs stay (s)"], abs=0.02)
    assert st["call_green"] == "BOX"
    # early in the stint the call is stay out, and the window opens later
    early = plan_from_state(specs, params, lap=2, compound=plan.compounds[0], age=2, used={plan.compounds[0]})
    assert early["call_green"] == "STAY" and early["box_window"][0] > 2
    assert plan_from_state(specs, params, lap=30, compound=plan.compounds[0], age=5, used={plan.compounds[0]}) is None


def test_plan_from_state_late_race_says_no_more_stops():
    from telemetry.strategy import plan_from_state

    params = RaceParams(laps=30, pit_loss_s=22.0, base_pace_s=90.0, wear_limit_pct=60.0)
    specs = _specs(0.6, 0.45, 0.3, wear=(8.0, 5.0, 3.5))
    # one stop done (soft then hard), 5 laps to go on fresh-ish hards: running to the flag is best
    st = plan_from_state(specs, params, lap=25, compound=20, age=6, used={18, 20})
    assert st["no_more_stops"] and st["call_green"] == "STAY"
    assert st["box_window"] is None or st["box_window"][1] < 30


# --------------------------------------------------------------------------- tyre-set inventory


def _brute_force_sets(specs, params, inventory):
    costs = _Costs(specs, params, inventory)
    best = float("inf")
    R = params.laps
    for n in range(1, params.max_stops + 2):
        for combo in itertools.product(costs.specs, repeat=n):
            if not costs.valid(frozenset(combo)):
                continue
            for cuts in itertools.combinations(range(1, R), n - 1):
                lens = np.diff([0, *cuts, R])
                best = min(best, _plan_cost(combo, tuple(int(x) for x in lens), costs))
    return best


def test_sets_dp_matches_brute_force_with_used_sets():
    params = RaceParams(laps=14, pit_loss_s=8.0, base_pace_s=90.0, max_stops=2, wear_limit_pct=40.0)
    specs = _specs(wear=(6.0, 4.0, 2.5))
    inv = {18: [0.0, 18.0], 19: [12.0], 20: [0.0]}
    plans = optimise(specs, params, inv)
    assert plans[0].race_time == pytest.approx(_brute_force_sets(specs, params, inv), abs=1e-6)


def test_no_inventory_is_the_old_model():
    params = RaceParams(laps=30, pit_loss_s=22.0, base_pace_s=90.0, wear_limit_pct=60.0)
    specs = _specs(0.6, 0.45, 0.3, wear=(8.0, 5.0, 3.5))
    plenty = {c: [0.0] * 4 for c in (18, 19, 20)}
    a, b = optimise(specs, params), optimise(specs, params, plenty)
    assert [(p.compounds, p.stints) for p in a] == [(p.compounds, p.stints) for p in b]
    assert a[0].race_time == pytest.approx(b[0].race_time)


def test_a_compound_runs_no_more_stints_than_you_have_sets():
    params = RaceParams(laps=40, pit_loss_s=18.0, base_pace_s=90.0)
    specs = _specs(0.9, 0.7, 0.5, wear=(3.0, 2.5, 2.0))
    free = optimise(specs, params)[0]
    assert max(free.compounds.count(c) for c in set(free.compounds)) >= 2  # the free plan repeats a compound
    inv = {18: [0.0], 19: [0.0], 20: [0.0]}
    for p in optimise(specs, params, inv):
        assert all(p.compounds.count(c) <= 1 for c in p.compounds)
    no_soft = optimise(specs, params, {19: [0.0, 0.0], 20: [0.0, 0.0]})
    assert no_soft and all(18 not in p.compounds for p in no_soft)


def test_a_used_set_is_slower_and_runs_fewer_laps():
    params = RaceParams(laps=30, pit_loss_s=22.0, base_pace_s=90.0, wear_limit_pct=60.0)
    specs = _specs(0.6, 0.45, 0.3, wear=(8.0, 5.0, 3.5))
    new = optimise(specs, params, {c: [0.0, 0.0] for c in (18, 19, 20)})[0]
    worn = optimise(specs, params, {c: [20.0, 20.0] for c in (18, 19, 20)})[0]
    assert worn.race_time > new.race_time
    assert all(w == 20.0 for w in worn.start_wear) and "(used 20%)" in worn.describe({s.code: s for s in specs})
    caps = {s.code: s.max_laps(60.0, 30, 20.0) for s in specs}  # (60 - 20) / rate
    assert caps == {18: 5, 19: 8, 20: 11}
    assert all(n <= caps[c] for c, n in zip(worn.compounds, worn.stints))
    assert float(np.sum(lap_times(worn, specs, params))) == pytest.approx(worn.race_time, abs=1e-6)


def test_a_set_past_the_wear_limit_is_not_used_and_freshest_goes_first():
    params = RaceParams(laps=30, pit_loss_s=22.0, base_pace_s=90.0, wear_limit_pct=60.0)
    specs = _specs(0.6, 0.45, 0.3, wear=(8.0, 5.0, 3.5))
    costs = _Costs(specs, params, {18: [70.0, 10.0, 0.0]})
    assert [s.wear for s in costs.sets[18]] == [0.0, 10.0]
    assert costs.n_sets(19) == 0
    assert optimise(specs, params, {18: [80.0], 19: [90.0], 20: [75.0]}) == []


def test_race_calls_and_live_fit_follow_the_sets():
    from telemetry.strategy import plan_from_state

    params = RaceParams(laps=30, pit_loss_s=22.0, base_pace_s=90.0, wear_limit_pct=60.0)
    specs = _specs(0.6, 0.45, 0.3, wear=(8.0, 5.0, 3.5))
    inv = {18: [0.0], 19: [0.0, 20.0], 20: [0.0]}
    plan = optimise(specs, params, inv)[0]
    calls = race_calls(plan, specs, params, inv)
    assert len(calls) == params.laps - 1
    # live: 8 laps to go on 5-lap-old softs; the free model fits a hard, with no hard left it cannot
    free = plan_from_state(specs, params, lap=22, compound=18, age=5, used={18})
    st = plan_from_state(specs, params, lap=22, compound=18, age=5, used={18}, inventory={19: [0.0]})
    assert free["fit_compound"] == 20 and free["sets_left"] is None
    assert st["fit_compound"] == 19 and st["sets_left"] == {"18": 0, "19": 1, "20": 0}
    used_m = plan_from_state(specs, params, lap=22, compound=18, age=5, used={18}, inventory={19: [25.0]})
    assert used_m["fit_compound"] == 19 and used_m["fit_wear"] == 25.0 and "(used 25%)" in used_m["fit_label"]
