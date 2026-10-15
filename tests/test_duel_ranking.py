"""Setup-duel ranking on synthetic contestants: weights, noise band, tie-breaks, wear cost with and without the model."""

from __future__ import annotations

import pytest

from telemetria_server.duel_ranking import FALLBACK_S_PER_PCT_LAP, W_QUALI, W_RACE, Contestant, rank_contestants


def laps(mean: float, spread: float = 0.0, n: int = 5) -> list[float]:
    """n laps around `mean` (symmetric, so the mean is exact); the best is mean - spread."""
    if n == 1:
        return [mean]
    step = 2 * spread / (n - 1)
    return [mean - spread + i * step for i in range(n)]


def balance(entry: float, mid: float, exit_: float) -> dict[str, float]:
    return {"entry": entry, "mid": mid, "exit": exit_}  # raw index; neutral is 2.0 / 3.0 / 0.2


NEUTRAL = balance(2.0, 3.0, 0.2)
UNDERSTEER = balance(4.5, 5.5, 2.5)


def test_score_weights_race_and_quali_and_orders_by_it():
    a = Contestant("a", "A", laps(90.0, 0.1))  # race 90.0, best 89.9
    b = Contestant("b", "B", laps(90.5, 0.8))  # race 90.5, best 89.7
    r = rank_contestants([a, b])
    by = {c["key"]: c for c in r["contestants"]}
    assert by["a"]["score_s"] == pytest.approx(W_RACE * 90.0 + W_QUALI * 89.9)
    assert by["b"]["score_s"] == pytest.approx(W_RACE * 90.5 + W_QUALI * 89.7)
    assert r["order"] == ["a", "b"] and r["winner"] == "a"
    assert (W_RACE, W_QUALI) == (0.7, 0.3)
    assert by["a"]["rank"] == 1 and by["a"]["delta_s"] == 0 and by["b"]["delta_s"] == pytest.approx(0.7 * 0.5 + 0.3 * -0.2)


def test_measurable_difference_decides_by_stopwatch():
    r = rank_contestants([Contestant("a", "A", laps(90.0)), Contestant("b", "B", laps(90.6))])
    assert r["tie_break"] == "stopwatch" and r["decided"]
    assert r["pairs"][0]["measurable"] is True
    assert r["noise_s"] == pytest.approx(0.10)  # floor with no spread


def test_noise_band_widens_with_spread():
    wide = laps(90.0, 0.8, 6)
    r = rank_contestants([Contestant("a", "A", wide), Contestant("b", "B", [t + 0.2 for t in wide])])
    assert r["noise_s"] > 0.2
    assert r["pairs"][0]["measurable"] is False


def test_inside_noise_balance_decides():
    a = Contestant("a", "A", laps(90.00), balance=UNDERSTEER)  # slightly quicker but far from neutral
    b = Contestant("b", "B", laps(90.05), balance=NEUTRAL)
    r = rank_contestants([a, b])
    assert r["pairs"][0]["measurable"] is False
    assert r["tie_break"] == "balance" and r["winner"] == "b"
    assert any("balance decides" in c for c in r["callouts"])
    assert r["contestants"][0]["balance"]["entry"]["label"] == "neutral"
    assert r["contestants"][1]["balance"]["mid"]["label"] == "understeer"


def test_inside_noise_similar_balance_falls_to_feel_then_to_nothing():
    a = Contestant("a", "A", laps(90.00), balance=NEUTRAL)
    b = Contestant("b", "B", laps(90.05), balance=balance(2.1, 3.0, 0.2))
    r = rank_contestants([a, b], feel_order=["b", "a"])
    assert r["tie_break"] == "feel" and r["winner"] == "b"
    r = rank_contestants([a, b])
    assert r["tie_break"] == "none" and not r["decided"]
    assert r["winner"] == "a"  # stopwatch order is kept, flagged as undecided
    assert any("No measurable difference" in c for c in r["callouts"])


def test_balance_unavailable_goes_straight_to_feel():
    a, b = Contestant("a", "A", laps(90.00)), Contestant("b", "B", laps(90.04))
    assert rank_contestants([a, b], feel_order=["b", "a"])["tie_break"] == "feel"


def test_feel_disagreement_is_called_out_when_the_stopwatch_decides():
    r = rank_contestants([Contestant("a", "A", laps(90.0)), Contestant("b", "B", laps(91.0))], feel_order=["b", "a"])
    assert r["winner"] == "a" and r["tie_break"] == "stopwatch"
    assert any("rated B first" in c for c in r["callouts"])


def test_three_contestants_cluster_only_the_ones_inside_the_band():
    a = Contestant("a", "A", laps(90.0), balance=UNDERSTEER)
    b = Contestant("b", "B", laps(90.04), balance=NEUTRAL)
    c = Contestant("c", "C", laps(91.5), balance=NEUTRAL)
    r = rank_contestants([a, b, c])
    assert r["order"] == ["b", "a", "c"] and r["tie_break"] == "balance"
    assert [p["measurable"] for p in r["pairs"] if "c" in (p["a"], p["b"])] == [True, True]


def test_wear_cost_from_the_model_is_relative_to_the_gentlest_setup():
    cost = {1.0: 4500.0, 2.0: 4560.0}  # race time per wear rate
    a = Contestant("a", "A", laps(90.0), wear_pct_per_lap=2.0)
    b = Contestant("b", "B", laps(90.3), wear_pct_per_lap=1.0)
    r = rank_contestants([a, b], plan_time=lambda w: cost[w], race_laps=30)
    by = {c["key"]: c for c in r["contestants"]}
    assert by["b"]["race_cost_s"] == 0 and by["a"]["race_cost_s"] == pytest.approx(60 / 30)
    assert r["cost_source"] == "model"
    assert r["winner"] == "b"  # 0.3 s slower on pace but 2 s per lap cheaper to run on tyres


def test_wear_cost_falls_back_to_a_fixed_factor_and_says_so():
    a = Contestant("a", "A", laps(90.0), wear_pct_per_lap=2.0)
    b = Contestant("b", "B", laps(90.3), wear_pct_per_lap=1.0)
    r = rank_contestants([a, b])
    by = {c["key"]: c for c in r["contestants"]}
    assert r["cost_source"] == "fallback"
    assert by["a"]["race_cost_s"] == pytest.approx(1.0 * FALLBACK_S_PER_PCT_LAP) and by["b"]["race_cost_s"] == 0
    assert "fixed" in r["cost_note"]


def test_model_without_a_plan_falls_back():
    a = Contestant("a", "A", laps(90.0), wear_pct_per_lap=2.0)
    b = Contestant("b", "B", laps(90.3), wear_pct_per_lap=1.0)
    r = rank_contestants([a, b], plan_time=lambda w: None, race_laps=30)
    assert r["cost_source"] == "fallback" and "no feasible plan" in r["cost_note"]


def test_no_wear_data_means_no_cost():
    r = rank_contestants([Contestant("a", "A", laps(90.0)), Contestant("b", "B", laps(91.0))])
    assert r["cost_source"] == "none" and all(c["race_cost_s"] == 0 for c in r["contestants"])


def test_missing_wear_for_one_contestant_uses_the_median_of_the_rest():
    a = Contestant("a", "A", laps(90.0), wear_pct_per_lap=2.0)
    b = Contestant("b", "B", laps(90.0))
    r = rank_contestants([a, b])
    assert all(c["race_cost_s"] == 0 for c in r["contestants"]) and "missing" in r["cost_note"]


def test_a_duel_needs_two_contestants_with_laps():
    with pytest.raises(ValueError):
        rank_contestants([Contestant("a", "A", laps(90.0))])
    with pytest.raises(ValueError):
        rank_contestants([Contestant("a", "A", laps(90.0)), Contestant("b", "B", [])])


def test_laps_from_different_sessions_widen_the_noise_band_and_warn():
    from telemetria_server.duel_ranking import CROSS_SESSION_NOISE_S

    def pair(sa, sb):
        return [Contestant("a", "A", laps(90.0), sessions=sa, balance=UNDERSTEER), Contestant("b", "B", laps(90.3), sessions=sb, balance=NEUTRAL)]

    same = rank_contestants(pair([1], [1, 2]))
    assert same["same_session"] is True and same["pairs"][0]["measurable"] is True and same["tie_break"] == "stopwatch"
    assert not any("different sessions" in c for c in same["callouts"])
    cross = rank_contestants(pair([27], [30, 31]))
    assert cross["same_session"] is False and cross["noise_s"] == CROSS_SESSION_NOISE_S == 0.5
    assert cross["pairs"][0]["measurable"] is False
    assert cross["tie_break"] == "balance" and cross["winner"] == "b"  # inside the widened band, balance decides as usual
    assert "Laps come from different sessions (#27 vs #30, #31)" in cross["callouts"][0]
    assert cross["contestants"][0]["sessions"] in ([27], [30, 31])


def test_unknown_sessions_count_as_the_same_session():
    assert rank_contestants([Contestant("a", "A", laps(90.0)), Contestant("b", "B", laps(91.0))])["same_session"] is True
