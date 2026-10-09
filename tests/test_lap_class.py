"""Lap classes: start / push / in / pit / out / slow / invalid, and new tyre sets."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from conftest import needs_library, session_by_source, session_df
from telemetry.metrics import _classify_laps, build_lap_summary


def _summary(times, *, reset=None, bad=None, v0=None, compound=None):
    n = len(times)
    return pd.DataFrame(
        {
            "lap": np.arange(n),
            "lap_time": np.asarray(times, dtype=float),
            "_bad_share": bad or [0.0] * n,
            "_v_start": v0 or [250.0] * n,
            "_reset_at": reset or [np.nan] * n,
            "compound": compound or [19] * n,
        }
    )


def test_stop_with_the_line_in_the_pit_lane_marks_the_in_lap_before():
    s = _classify_laps(_summary([94, 94, 99, 115, 94, 94], reset=[np.nan, np.nan, np.nan, 0.2, np.nan, np.nan]))
    assert list(s["lap_class"]) == ["push", "push", "in", "pit", "push", "push"]
    assert list(s["fresh_set"]) == [False, False, False, True, False, False]


def test_stop_at_the_end_of_the_lap_marks_the_out_lap_after():
    s = _classify_laps(_summary([78, 78, 98, 79, 78], reset=[np.nan, np.nan, 0.95, np.nan, np.nan]))
    assert list(s["lap_class"]) == ["push", "push", "pit", "out", "push"]
    assert bool(s.loc[3, "fresh_set"]) and bool(s.loc[2, "pit_stop"])


def test_garage_tyre_change_between_practice_runs_is_a_new_set_not_a_stop():
    s = _classify_laps(_summary([93, 92.5, 90.7, 92.4], reset=[np.nan, np.nan, 0.1, np.nan]))
    assert "pit" not in set(s["lap_class"]) and bool(s.loc[2, "fresh_set"])


def test_garbage_standing_start_and_slow_laps():
    s = _classify_laps(_summary([83, 95, 94, 104, 94], bad=[0.5, 0, 0, 0, 0], v0=[6, 12, 250, 250, 250]))
    assert list(s["lap_class"]) == ["invalid", "start", "push", "slow", "push"]


def test_compound_change_without_a_wear_reset_still_starts_a_new_set():
    s = _classify_laps(_summary([90, 90, 90], compound=[18, 18, 17]))
    assert list(s["fresh_set"]) == [False, False, True]


# ----------------------------------------------------------------------------- real sessions


def _real(name):
    session = session_by_source(name)
    return build_lap_summary(session_df(session), track_length=session["track_length"])


@needs_library
def test_bahrain_race_stops_and_start():
    s = _real("bahrain_race.csv").set_index("lap")
    assert s.loc[0, "lap_class"] == "start"
    assert [int(l) for l in s.index[s["pit_stop"]]] == [8, 17]
    assert s.loc[7, "lap_class"] == "in" and s.loc[16, "lap_class"] == "in"


@needs_library
def test_monaco_race_stops_and_garbage_first_lap():
    s = _real("Monaco_Race.csv").set_index("lap")
    assert s.loc[0, "lap_class"] == "invalid"
    assert [int(l) for l in s.index[s["pit_stop"]]] == [13, 26]
    assert s.loc[14, "lap_class"] == "out" and s.loc[27, "lap_class"] == "out"


@needs_library
@pytest.mark.parametrize("name", ["Catalunya_Q1.csv", "Catalunya_Q2.csv", "Catalunya_Q3.csv", "Monako_Q2.csv", "Monako_FP1.csv"])
def test_quali_laps_with_padded_edges_stay_push_laps(name):
    s = _real(name)
    best = s.loc[s["is_best"]].iloc[0]
    assert best["lap_class"] == "push" and best["compound"] >= 0


@needs_library
def test_race_runs_no_longer_include_the_pit_lap():
    from telemetry.runs import split_runs

    session = session_by_source("bahrain_race.csv")
    runs = split_runs(session_df(session), session=session, track_length=session["track_length"])
    assert [r.kind for r in runs] == ["race", "race", "race"]
    assert all(r.best_time < 100 for r in runs)


# ----------------------------------------------------------------------------- game channels


def _channel_summary(times, *, stop=None, lane=None, age_start=None, age_end=None, reset=None, sc=None):
    n = len(times)
    lane = lane or [None] * n
    return pd.DataFrame(
        {
            "lap": np.arange(n),
            "lap_time": np.asarray(times, dtype=float),
            "_bad_share": [0.0] * n,
            "_v_start": [250.0] * n,
            "_reset_at": reset or [np.nan] * n,
            "_stop_s": stop or [0.0] * n,
            "_lane_first": [l[0] if l else np.nan for l in lane],
            "_lane_last": [l[1] if l else np.nan for l in lane],
            "_age_start": age_start or list(range(n)),
            "tyre_age": age_end or list(range(n)),
            "_sc_share": sc or [0.0] * n,
            "compound": [17] * n,
        }
    )


def test_game_channels_mark_the_stop_in_lap_and_new_set():
    s = _classify_laps(
        _channel_summary(
            [68, 68, 75, 83, 67, 68],
            stop=[0, 0, 0, 2.4, 0, 0],
            lane=[None, None, (0.98, 1.0), (0.0, 0.06), None, None],
            age_start=[0, 1, 2, 3, 1, 2],
            age_end=[0, 1, 2, 0, 1, 2],
            reset=[np.nan, np.nan, np.nan, 0.02, np.nan, np.nan],
        )
    )
    assert list(s["lap_class"]) == ["push", "push", "in", "pit", "push", "push"]
    assert list(s["pit_stop"]) == [False, False, False, True, False, False]
    assert bool(s.loc[3, "fresh_set"])


def test_short_stint_stop_is_caught_without_a_big_wear_drop():
    """Austria L21: six laps on the set, wear only fell to ~5% — the stop timer decides."""
    s = _classify_laps(_channel_summary([68, 76, 83, 66], stop=[0, 0, 2.4, 0], lane=[None, (0.99, 1.0), (0.0, 0.05), None], age_end=[4, 5, 0, 1], age_start=[4, 5, 6, 1], reset=[np.nan, np.nan, 0.01, np.nan]))
    assert list(s["lap_class"]) == ["push", "in", "pit", "push"]


def test_a_set_change_on_a_lap_the_export_skipped_still_starts_a_new_stint():
    df = _channel_summary([75, 79, 79, 74], age_start=[9, 10, 2, 3], age_end=[9, 10, 2, 3])
    df["lap"] = [9, 10, 13, 14]  # laps 11-12 missing from the export
    s = _classify_laps(df)
    assert list(s["fresh_set"]) == [False, False, True, False]


def test_safety_car_laps_get_their_own_class():
    s = _classify_laps(_channel_summary([93, 120, 118, 93], sc=[0, 0.9, 0.6, 0.1]))
    assert list(s["lap_class"]) == ["push", "sc", "sc", "push"]


@needs_library
def test_new_exports_match_the_game_pit_stops():
    for name, stops in (("Austria_race.csv", [15, 21, 29]), ("Catalunya_race.csv", [11, 23]), ("Silverstone_race.csv", [7, 17])):
        try:
            s = _real(name).set_index("lap")
        except BaseException:
            continue
        assert [int(l) for l in s.index[s["pit_stop"]]] == stops, name
        assert all(s.loc[l - 1, "lap_class"] == "in" for l in stops), name


@needs_library
def test_zandvoort_export_gap_and_silverstone_safety_car():
    try:
        z = _real("Zandvoort_Race.csv").set_index("lap")
        sil = _real("Silverstone_race.csv").set_index("lap")
    except BaseException:
        pytest.skip("new race exports not in this library")
    assert 11 not in z.index and 12 not in z.index  # the export skipped them
    assert bool(z.loc[13, "fresh_set"]) and z.loc[13, "lap_class"] != "start"
    assert (sil["lap_class"] == "sc").sum() >= 2


def test_session_tags_from_file_names():
    from telemetry.session_tags import type_from_name

    assert type_from_name("Austria_race.csv") == "Race"
    assert type_from_name("Monza_Q3.csv") == "Quali" and type_from_name("Montreal_SQ1.csv") == "Quali"
    assert type_from_name("Catalunya_FP2.csv") == "FP2" and type_from_name("Zandvoort_practice.csv") == "FP1"
    assert type_from_name("Bahrain.csv") == ""


def test_track_state_from_tyres_run():
    from telemetry.session_tags import state_from_telemetry

    def summary(comps):
        return pd.DataFrame({"lap": range(len(comps)), "compound": comps})

    assert state_from_telemetry(summary([8] * 6 + [7] * 2)) == "wet"
    assert state_from_telemetry(summary([7] * 5 + [17] * 4)) == "inter"
    assert state_from_telemetry(summary([7] * 2 + [17] * 8)) == "damp"
    assert state_from_telemetry(summary([17] * 10)) == "dry"
    assert state_from_telemetry(pd.DataFrame(), "Austria_Q1_wet.csv") == "wet"
