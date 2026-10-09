"""Checks against the personal Catalunya sessions; skipped when the library is not present."""

from __future__ import annotations

import shutil

import pytest

from conftest import DB_PATH, ROOT, needs_library, session_by_source, session_df

pytestmark = needs_library


def test_reset_garage_on_the_last_lap_is_not_returned_as_setup():
    from telemetry.loader import is_reset_setup, setup_from_telemetry

    df = session_df(session_by_source("Catalunya_Q2.csv"))
    for lap in sorted(df["lap"].unique()):
        setup = setup_from_telemetry(df, int(lap))
        assert not is_reset_setup(setup), f"lap {lap} returned the post-session reset garage"
        assert setup["wing_setup_0"] > 0 and setup["susp_spring_setup_0"] > 1


def test_fp2_splits_on_the_mid_session_pressure_change_and_corrects_for_fuel():
    from telemetry.runs import split_runs

    session = session_by_source("Catalunya_FP2.csv")
    runs = split_runs(session_df(session), session=session, track_length=session["track_length"])
    assert len(runs) >= 2
    assert runs[0].mech_fp != runs[1].mech_fp  # tyre pressures were changed after lap 2
    for r in runs:
        assert r.best_corrected == pytest.approx(r.best_time, abs=0.6)  # ~3-6 kg of fuel only


def test_q1_to_q2_is_a_front_wing_only_change():
    from telemetry.setup_eval import compare_sessions_runs

    q1, q2 = session_by_source("Catalunya_Q1.csv"), session_by_source("Catalunya_Q2.csv")
    comp = compare_sessions_runs(q1["id"], q2["id"], "quali", ROOT, with_corners=False)
    assert comp is not None
    assert [(d["key"], d["delta"]) for d in comp.setup_diff] == [("wing_setup_0", -2.0)]


def test_identical_garage_still_moves_more_than_the_naive_noise_floor():
    """Q2 -> Q3 ran the same setup; the verdict machinery must be able to see that variation."""
    from telemetry.setup_eval import NOISE_FLOOR, compare_sessions_runs

    q2, q3 = session_by_source("Catalunya_Q2.csv"), session_by_source("Catalunya_Q3.csv")
    comp = compare_sessions_runs(q2["id"], q3["id"], "quali", ROOT, with_corners=False)
    assert comp is not None and comp.setup_diff == []
    assert abs(comp.pace_delta) > 0.5 and NOISE_FLOOR["quali"] >= 0.2


def test_recommendation_lifecycle_end_to_end(tmp_path):
    """Advice on Q1 -> Q2 garage -> journal marks it applied and records a measured experiment."""
    from telemetry.db import get_session
    from telemetry.setup_log import evaluate_track, get_recommendations, list_experiments, save_recommendation

    from telemetry.setup_history import list_track_sessions

    names = ["Catalunya_FP1.csv", "Catalunya_FP2.csv", "Catalunya_Q1.csv", "Catalunya_Q2.csv", "Catalunya_Q3.csv"]
    sessions = {n: session_by_source(n) for n in names}
    (tmp_path / "data" / "sessions").mkdir(parents=True)
    shutil.copy(DB_PATH, tmp_path / "data" / "telemetry.db")
    # Every session on the track: the journal evaluates all of them (later imports included).
    for path in list_track_sessions("Catalunya", ROOT)["telemetry_path"]:
        shutil.copy(ROOT / path, tmp_path / path)

    q1, q2 = sessions["Catalunya_Q1.csv"], sessions["Catalunya_Q2.csv"]
    save_recommendation(
        session_id=q1["id"],
        track="Catalunya",
        variant="quali",
        conditions="",
        base_setup={"wing_setup_0": 40.0},
        proposed_setup={"wing_setup_0": 38.0},
        changes=[{"key": "wing_setup_0", "label": "Front wing", "before": 40.0, "after": 38.0, "reason": "test"}],
        diagnosis={"issue": "understeer", "phase": "mid"},
        app_root=tmp_path,
    )
    save_recommendation(
        session_id=q2["id"],
        track="Catalunya",
        variant="quali",
        conditions="",
        base_setup={"arb_setup_0": 1.0},
        proposed_setup={"arb_setup_0": 5.0},
        changes=[{"key": "arb_setup_0", "label": "Front ARB", "before": 1.0, "after": 5.0, "reason": "test"}],
        diagnosis={"issue": "understeer", "phase": "mid"},
        app_root=tmp_path,
    )

    evaluate_track("Catalunya", tmp_path)

    recs = {r["session_id"]: r for r in get_recommendations(tmp_path)}
    assert recs[q1["id"]]["status"] == "applied" and recs[q1["id"]]["followup_session_id"] == q2["id"]
    assert recs[q2["id"]]["status"] == "ignored"  # Q3 kept the Q2 garage

    exps = {(e["from_session_id"], e["to_session_id"]): e for e in list_experiments("Catalunya", tmp_path)}
    exp = exps[(q1["id"], q2["id"])]
    assert exp["source"] == "recommended" and [c["key"] for c in exp["changes"]] == ["wing_setup_0"]
    assert exp["recommendation_id"] == recs[q1["id"]]["id"]
    assert get_session(q2["id"], tmp_path) is not None

    # Idempotent: a second pass with nothing new does no work and changes nothing.
    again = evaluate_track("Catalunya", tmp_path)
    assert again["skipped"] == 1 or again["experiments"] == len(exps)


def _build(history=None, base=None):
    from telemetry.loader import setup_from_telemetry
    from telemetry.setup_builder import build_setup_from_practice

    session = session_by_source("Catalunya_Q2.csv")
    df = session_df(session)
    stored = setup_from_telemetry(df, 0)
    return stored, build_setup_from_practice(
        df, stored, "Catalunya", variant="quali", lap=0, history=history, base=base
    )


def test_builder_backs_out_a_slower_front_wing_cut_end_to_end():
    from telemetry.setup_log import SetupHistory

    history = SetupHistory(
        track="Barcelona",
        mode="quali",
        state="dry",
        last_experiment={
            "verdict": "worse",
            "pace_delta": 0.6,
            "from_session_id": 18,
            "to_session_id": 19,
            "changes": [{"key": "wing_setup_0", "from": 40.0, "to": 38.0, "delta": -2.0}],
        },
    )
    stored, built = _build(history)
    assert stored["wing_setup_0"] == 38.0
    rows = [c for c in built.changes if c.key == "wing_setup_0"]
    assert len(rows) == 1  # the revert and any understeer nudge are shown as one move
    assert rows[0].locked and rows[0].before == 38.0 and "Back out" in rows[0].reason
    # The understeer read may then add front wing on top of the restored value, never below it.
    assert rows[0].after == built.setup["wing_setup_0"] >= 40.0
    assert any("backed out" in f for f in built.findings)


def test_builder_without_history_is_unchanged_by_the_learning_layer():
    _, plain = _build(None)
    from telemetry.setup_log import SetupHistory

    _, empty = _build(SetupHistory(track="Barcelona", mode="quali", state="dry"))
    assert plain.setup == empty.setup
    assert [c.key for c in plain.changes] == [c.key for c in empty.changes]


def test_builder_can_start_from_the_best_verified_setup():
    from telemetry.loader import setup_from_telemetry
    from telemetry.setup_log import SetupHistory

    q1 = session_by_source("Catalunya_Q1.csv")
    verified = setup_from_telemetry(session_df(q1), 1)
    history = SetupHistory(
        track="Barcelona",
        mode="quali",
        state="dry",
        best_verified={"setup": verified, "session_id": q1["id"], "pace": 75.5, "compound": 18, "laps": 3},
    )
    _, built = _build(history, base="best_verified")
    assert built.base_source.startswith("Best verified setup")
    assert verified["wing_setup_0"] == 40.0  # Q1 ran 40; the Q2 session garage ran 38
    assert built.setup["wing_setup_0"] >= 40.0  # started from 40 (+ any understeer nudge), not from 38
