"""Tyre engineering: degradation fit, pressures, stints, pit loss and the track compound model."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from conftest import ROOT, needs_library, session_by_source
from telemetry.tyres import (
    TyreTargets,
    fit_degradation,
    measure_pit_losses,
    pressure_recommendation,
    tyre_stints,
)


def test_degradation_fit_recovers_the_slope():
    ages = np.arange(10, dtype=float)
    fit = fit_degradation(ages, 90.0 + 0.2 * ages)
    assert fit.slope == pytest.approx(0.2, abs=1e-6) and fit.intercept == pytest.approx(90.0, abs=1e-6)
    assert fit.cliff_age is None


def test_degradation_fit_finds_a_cliff():
    ages = np.arange(12, dtype=float)
    times = 90.0 + 0.05 * ages + np.where(ages >= 7, 0.8 * (ages - 6), 0.0)
    fit = fit_degradation(ages, times)
    assert fit.cliff_age in (6, 7, 8)


def test_degradation_needs_three_laps():
    assert fit_degradation(np.array([0.0, 1.0]), np.array([90.0, 90.2])).slope is None


def test_pressure_recommendation_moves_the_cold_set_by_the_hot_error():
    hot = {"RL": 24.0, "RR": 23.8, "FL": 21.6, "FR": 21.6}
    cold = {0: 23.5, 1: 23.5, 2: 21.0, 3: 21.0}
    rec = pressure_recommendation(hot, cold, TyreTargets(19, 80, 100, hot_front_psi=22.0, hot_rear_psi=23.0)).set_index("Wheel")
    assert rec.loc["RL", "Build-up (psi)"] == pytest.approx(0.5)
    assert rec.loc["RL", "Cold set → (psi)"] == pytest.approx(22.5)
    assert rec.loc["FL", "Change (psi)"] == pytest.approx(0.4)


def test_stints_split_on_new_sets_and_take_the_majority_compound():
    summary = pd.DataFrame(
        {
            "lap": range(6),
            "lap_class": ["start", "push", "in", "pit", "push", "push"],
            "fresh_set": [False, False, False, True, False, False],
            "compound": [19, 19, 19, 19, 20, 20],
        }
    )
    stints = tyre_stints(summary)
    assert [s.laps for s in stints] == [[0, 1, 2], [3, 4, 5]]
    assert [s.compound for s in stints] == [19, 20]
    assert stints[1].push_laps == [4, 5] and stints[1].ages[5] == 2


@needs_library
def test_bahrain_race_pit_losses_and_stints():
    from telemetry.tyres import session_frames, summarize_stints

    sid = session_by_source("bahrain_race.csv")["id"]
    session, df, summary = session_frames(sid, ROOT)
    losses = measure_pit_losses(summary)
    assert len(losses) == 2 and all(18 < x < 35 for x in losses)
    summaries, tbl = summarize_stints(df, summary, session=session)
    assert [s.stint.compound for s in summaries] == [19, 19, 20]
    assert [s.stint.n_laps for s in summaries] == [8, 9, 12]
    assert all(s.limiting_wheel == "RL" for s in summaries)  # the left-rear eats itself at Bahrain
    assert {"T_FL", "P_RL", "W_FR", "Twin_RR"} <= set(tbl.columns)


@needs_library
def test_monaco_stint_wear_is_the_max_not_the_reset_lap():
    from telemetry.tyres import session_frames, summarize_stints

    sid = session_by_source("Monaco_Race.csv")["id"]
    session, df, summary = session_frames(sid, ROOT)
    summaries, _ = summarize_stints(df, summary, session=session)
    assert summaries[0].wear_now > 40  # the stop lap ends on the new set at 0%


@needs_library
def test_track_model_measures_compounds_with_the_library_fuel_effect():
    from telemetry.tyres import library_race_stats, track_compound_model

    stats = library_race_stats(ROOT)
    model = track_compound_model("Bahrain", "dry", ROOT)
    assert model.ref_compound == 19 and model.compounds[19].source == "measured"
    assert model.compounds[18].source == "assumed"  # C3 never ran a long stint
    assert model.pit_loss is not None and 18 < model.pit_loss < 35
    assert model.race_laps_seen == 29
    if stats.fuel_pairs >= 3:
        # With fuel + track evolution measured, the harder C1 is no longer "faster" than C2.
        assert model.compounds[20].offset_s > model.compounds[19].offset_s


@needs_library
def test_library_race_stats_measure_fuel_effect_and_box_wear():
    from telemetry.tyres import FUEL_EFFECT_RANGE, library_race_stats

    stats = library_race_stats(ROOT)
    lo, hi = FUEL_EFFECT_RANGE
    assert stats.fuel_pairs == 0 or lo <= stats.fuel_s_per_kg <= hi
    assert stats.box_wear_pct is None or 40 < stats.box_wear_pct < 95


@needs_library
def test_wet_race_gives_a_wet_model_with_wet_tyres_only():
    from telemetry.tyres import track_compound_model

    try:
        session_by_source("Hungaroring_Race.csv")
    except BaseException:
        pytest.skip("Hungaroring race not in this library")
    model = track_compound_model("Hungaroring", "inter", ROOT)
    assert model.compounds and set(model.compounds) <= {7, 8}
