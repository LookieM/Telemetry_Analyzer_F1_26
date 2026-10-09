"""Journal, lever statistics and builder learning — synthetic, no personal data needed."""

from __future__ import annotations

import json

from telemetry.db import connect
from telemetry.setup_builder import (
    SetupChange,
    _apply_history,
    _enforce_change_budget,
    _revert_last_experiment,
)
from telemetry.setup_log import SetupHistory, lever_stats, match_application, save_recommendation

TRACK = "Barcelona"


def _changes(*rows):
    return [{"key": k, "before": b, "after": a, "label": k, "reason": "t"} for k, b, a in rows]


# ----------------------------------------------------------------------------- match_application


def test_match_application_full_partial_ignored_and_opposite():
    advised = _changes(("wing_setup_0", 38, 40), ("arb_setup_0", 10, 9), ("diff_onThrottle_setup", 0.6, 0.7))

    full = match_application(advised, {"wing_setup_0": 40, "arb_setup_0": 9, "diff_onThrottle_setup": 0.7})
    assert full.status == "applied" and full.frac == 1.0

    partial = match_application(advised, {"wing_setup_0": 40, "arb_setup_0": 10, "diff_onThrottle_setup": 0.6})
    assert partial.status == "partial" and partial.applied == ["wing_setup_0"]

    ignored = match_application(advised, {"wing_setup_0": 38, "arb_setup_0": 10, "diff_onThrottle_setup": 0.6})
    assert ignored.status == "ignored" and ignored.frac == 0.0

    wrong_way = match_application(advised, {"wing_setup_0": 36, "arb_setup_0": 10, "diff_onThrottle_setup": 0.6})
    assert wrong_way.opposite == ["wing_setup_0"] and wrong_way.status == "ignored"


def test_match_application_half_the_delta_counts_and_flags_manual_extras():
    advised = _changes(("wing_setup_0", 38, 42))
    app = match_application(
        advised,
        {"wing_setup_0": 40, "toe_setup_0": 0.05, "fuel_setup": 5},
        old_setup={"wing_setup_0": 38, "toe_setup_0": 0.0, "fuel_setup": 40},
    )
    assert app.applied == ["wing_setup_0"]  # moved exactly 50% of the advised delta
    assert app.extra == ["toe_setup_0"]  # fuel is a load, not a setup change


# ----------------------------------------------------------------------------- lever statistics


def _add_experiment(root, frm, to, verdict, pace, noise, changes, issue="understeer", phase="mid", track=TRACK):
    with connect(root) as conn:
        conn.execute(
            """
            INSERT INTO setup_experiments (track, from_session_id, to_session_id, mode, conditions_state,
                changes_json, source, pace_delta, noise, balance_delta_json, symptom_json, verdict, created_at)
            VALUES (?, ?, ?, 'quali', 'dry', ?, 'manual', ?, ?, '{}', ?, ?, 'now')
            """,
            (
                track,
                frm,
                to,
                json.dumps([{"key": k, "delta": d} for k, d in changes]),
                pace,
                noise,
                json.dumps({"issue": issue, "phase": phase, "fixed": verdict == "better"}),
                verdict,
            ),
        )


def test_lever_stats_counts_only_matching_symptom_and_ignores_inconclusive(tmp_root):
    _add_experiment(tmp_root, 1, 2, "worse", 0.4, 0.25, [("wing_setup_0", 2.0)])
    _add_experiment(tmp_root, 2, 3, "worse", 0.3, 0.25, [("wing_setup_0", 2.0)])
    _add_experiment(tmp_root, 3, 4, "inconclusive", 1.0, 0.25, [("wing_setup_0", 2.0)])
    _add_experiment(tmp_root, 4, 5, "better", -0.5, 0.25, [("arb_setup_0", -1.0)])
    _add_experiment(tmp_root, 5, 6, "worse", 0.6, 0.25, [("toe_setup_0", 0.02)], issue="oversteer", phase="exit")

    stats = lever_stats(TRACK, "understeer", "mid", tmp_root)
    assert stats[("wing_setup_0", 1)].hurt == 2.0
    assert stats[("arb_setup_0", -1)].helped == 1.0
    assert ("toe_setup_0", 1) not in stats  # different symptom


def test_lever_stats_many_changes_do_not_blame_one_lever(tmp_root):
    many = [("wing_setup_0", 2.0), ("wing_setup_1", 2.0), ("arb_setup_0", 1.0), ("arb_setup_1", 1.0), ("toe_setup_0", 0.01)]
    _add_experiment(tmp_root, 1, 2, "worse", 0.8, 0.25, many)
    stats = lever_stats(TRACK, "understeer", "mid", tmp_root)
    assert stats[("wing_setup_0", 1)].hurt == 0.0  # confounded: counted for pace mean only
    assert stats[("wing_setup_0", 1)].mean_pace is not None


def test_other_tracks_count_at_half_weight(tmp_root):
    _add_experiment(tmp_root, 1, 2, "worse", 0.4, 0.25, [("wing_setup_0", 2.0)], track="Monaco")
    _add_experiment(tmp_root, 3, 4, "worse", 0.4, 0.25, [("wing_setup_0", 2.0)], track="Monaco")
    st = lever_stats(TRACK, "understeer", "mid", tmp_root)[("wing_setup_0", 1)]
    assert st.hurt == 1.0
    history = SetupHistory(track=TRACK, mode="quali", state="dry", levers={("wing_setup_0", 1): st})
    assert history.should_avoid("wing_setup_0", 1) is None  # two foreign tracks are not enough


def test_one_clearly_bad_experiment_on_this_track_is_enough(tmp_root):
    _add_experiment(tmp_root, 1, 2, "worse", 0.6, 0.25, [("wing_setup_0", 2.0)])  # 2.4x noise
    st = lever_stats(TRACK, "understeer", "mid", tmp_root)[("wing_setup_0", 1)]
    history = SetupHistory(track=TRACK, mode="quali", state="dry", levers={("wing_setup_0", 1): st})
    assert history.should_avoid("wing_setup_0", 1) is not None


# ----------------------------------------------------------------------------- builder learning


def _history(tmp_root, experiments, **kw):
    for i, (verdict, pace, changes) in enumerate(experiments):
        _add_experiment(tmp_root, i + 1, i + 2, verdict, pace, 0.25, changes)
    levers = lever_stats(TRACK, "understeer", "mid", tmp_root)
    return SetupHistory(track=TRACK, mode="quali", state="dry", levers=levers, **kw)


def test_builder_skips_a_lever_that_hurt_this_symptom_before(tmp_root):
    history = _history(tmp_root, [("worse", 0.7, [("wing_setup_0", 2.0)])])
    base = {"wing_setup_0": 38.0, "arb_setup_0": 10.0}
    changes = [
        SetupChange("wing_setup_0", "Front wing", 38.0, 40.0, "More front wing vs push"),
        SetupChange("arb_setup_0", "Front anti-roll bar", 10.0, 9.0, "Softer front ARB"),
    ]
    findings: list[str] = []
    kept, _ = _apply_history(base, changes, history, {"issue": "understeer"}, findings)
    assert [c.key for c in kept] == ["arb_setup_0"]
    assert any("Skipped Front wing" in f for f in findings)


def test_builder_continues_a_lever_that_helped_and_promotes_its_group(tmp_root):
    history = _history(tmp_root, [("better", -0.5, [("arb_setup_0", -2.0)])])
    base = {"wing_setup_0": 38.0, "arb_setup_0": 10.0}
    changes = [SetupChange("wing_setup_0", "Front wing", 38.0, 40.0, "More front wing vs push")]
    findings: list[str] = []
    kept, first = _apply_history(base, changes, history, {"issue": "understeer"}, findings)
    cont = [c for c in kept if c.key == "arb_setup_0"]
    assert cont and cont[0].after < cont[0].before and "Continue" in cont[0].reason
    assert "mech" in first


def test_builder_does_not_continue_when_balance_is_fine(tmp_root):
    history = _history(tmp_root, [("better", -0.5, [("arb_setup_0", -2.0)])])
    kept, _ = _apply_history({"arb_setup_0": 10.0}, [], history, {"issue": "balanced"}, [])
    assert kept == []


def test_revert_first_backs_out_a_clearly_slower_experiment():
    history = SetupHistory(
        track=TRACK,
        mode="quali",
        state="dry",
        last_experiment={
            "verdict": "worse",
            "pace_delta": 0.55,
            "from_session_id": 18,
            "to_session_id": 19,
            "changes": [{"key": "wing_setup_0", "from": 40.0, "to": 38.0, "delta": -2.0}],
        },
    )
    setup = {"wing_setup_0": 38.0, "wing_setup_1": 28.0}
    changes: list[SetupChange] = []
    findings: list[str] = []
    _revert_last_experiment(setup, history, changes, findings)
    assert setup["wing_setup_0"] == 40.0
    assert changes[0].locked and "Back out" in changes[0].reason
    assert any("backed out" in f for f in findings)


def test_revert_skips_moves_you_already_undid_and_big_change_sets():
    exp = {
        "verdict": "worse",
        "pace_delta": 0.5,
        "from_session_id": 1,
        "to_session_id": 2,
        "changes": [{"key": "wing_setup_0", "from": 40.0, "to": 38.0, "delta": -2.0}],
    }
    history = SetupHistory(track=TRACK, mode="quali", state="dry", last_experiment=exp)
    setup = {"wing_setup_0": 40.0}  # already back at the old value
    changes: list[SetupChange] = []
    _revert_last_experiment(setup, history, changes, [])
    assert changes == []

    exp["changes"] = [{"key": f"k{i}", "from": 1.0, "to": 2.0, "delta": 1.0} for i in range(6)]
    big_setup = {f"k{i}": 2.0 for i in range(6)}
    findings: list[str] = []
    _revert_last_experiment(big_setup, history, changes, findings)
    assert changes == [] and any("too many" in f for f in findings)


def test_neutral_or_better_last_experiment_is_never_reverted():
    for verdict in ("better", "neutral", "inconclusive"):
        history = SetupHistory(
            track=TRACK,
            mode="quali",
            state="dry",
            last_experiment={"verdict": verdict, "changes": [{"key": "wing_setup_0", "from": 40.0, "to": 38.0, "delta": -2.0}]},
        )
        setup = {"wing_setup_0": 38.0}
        changes: list[SetupChange] = []
        _revert_last_experiment(setup, history, changes, [])
        assert changes == [] and setup["wing_setup_0"] == 38.0


def test_budget_keeps_locked_reverts_outside_the_group_limit():
    changes = [
        SetupChange("wing_setup_0", "Front wing", 38, 40, "Back out", locked=True),
        SetupChange("brake_bias_setup", "Brake bias", 0.56, 0.57, "Forward bias vs lock"),
        SetupChange("arb_setup_0", "ARB F", 10, 9, "Softer ARB"),
        SetupChange("diff_onThrottle_setup", "Diff", 0.6, 0.7, "Tighter diff"),
        SetupChange("tyre_press_setup_0", "Press", 160000, 161000, "Hot tyres"),
    ]
    kept = _enforce_change_budget(changes, max_groups=3)
    keys = [c.key for c in kept]
    assert "wing_setup_0" in keys  # locked revert survives although aero and mech are exclusive
    assert "arb_setup_0" in keys and "brake_bias_setup" in keys
    assert len(keys) == 5 - 1  # tyres group dropped by the 3-group budget


def test_first_groups_jump_the_queue():
    changes = [
        SetupChange("brake_bias_setup", "Brake bias", 0.56, 0.57, "Forward bias vs lock"),
        SetupChange("diff_onThrottle_setup", "Diff", 0.6, 0.7, "Tighter diff"),
        SetupChange("arb_setup_0", "ARB F", 10, 9, "Softer ARB"),
        SetupChange("tyre_press_setup_0", "Press", 160000, 161000, "Hot tyres"),
    ]
    kept = [c.key for c in _enforce_change_budget(changes, max_groups=2, first_groups=("tyres",))]
    assert "tyre_press_setup_0" in kept and "brake_bias_setup" in kept
    assert "arb_setup_0" not in kept


# ----------------------------------------------------------------------------- journal storage


def test_save_recommendation_is_an_upsert_that_resets_follow_up(tmp_root):
    changes = [SetupChange("wing_setup_0", "Front wing", 38.0, 40.0, "x"), SetupChange("fuel_setup", "Fuel", 40, 5, "y")]
    kw = dict(
        session_id=7,
        track="Catalunya",
        variant="Quali",
        conditions="",
        base_setup={"wing_setup_0": 38.0},
        proposed_setup={"wing_setup_0": 40.0},
        diagnosis={"issue": "understeer"},
        app_root=tmp_root,
    )
    first = save_recommendation(changes=changes, **kw)
    with connect(tmp_root) as conn:
        conn.execute("UPDATE setup_recommendations SET status='applied', followup_session_id=8 WHERE id=?", (first,))
    second = save_recommendation(changes=changes[:1], **kw)
    assert first == second
    from telemetry.setup_log import get_recommendations

    (rec,) = get_recommendations(tmp_root)
    assert rec["status"] == "pending" and rec["followup_session_id"] is None
    assert [c["key"] for c in rec["changes"]] == ["wing_setup_0"]
    assert rec["track"] == "Barcelona"  # alias normalised so lookups match


def test_deleting_the_follow_up_session_returns_the_advice_to_pending(tmp_root):
    from telemetry.db import delete_session
    from telemetry.setup_log import get_recommendations

    with connect(tmp_root) as conn:
        for sid in (7, 8):
            conn.execute(
                "INSERT INTO sessions (id, created_at, source_name, source_hash, track, telemetry_path) "
                "VALUES (?, 'now', ?, ?, 'Catalunya', ?)",
                (sid, f"s{sid}.csv", f"hash{sid}", f"data/sessions/s{sid}.parquet"),
            )
    rec_id = save_recommendation(
        session_id=7,
        track="Catalunya",
        variant="quali",
        conditions="",
        base_setup={"wing_setup_0": 38.0},
        proposed_setup={"wing_setup_0": 40.0},
        changes=[SetupChange("wing_setup_0", "Front wing", 38.0, 40.0, "x")],
        app_root=tmp_root,
    )
    with connect(tmp_root) as conn:
        conn.execute(
            "UPDATE setup_recommendations SET status='ignored', followup_session_id=8, applied_frac=0.0 WHERE id=?",
            (rec_id,),
        )

    delete_session(8, tmp_root)

    (rec,) = get_recommendations(tmp_root)
    assert rec["status"] == "pending" and rec["followup_session_id"] is None and rec["applied_frac"] is None
