"""Setup generator: the pure estimator on synthetic evidence, fuel planning, and the library fuel samples."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from telemetry import db
from telemetry import setup_generator as sg
from telemetry.setup_builder import CAMBER_META
from telemetry.setup_tweaker import SETUP_PARAMS, psi_to_pa
from telemetry.track_catalog import TRACK_LENGTHS_M, race_laps

PRIOR, _ = sg.prior_for("Monza")


def ev(track, source, sim, **setup):
    """Evidence from a track whose typical setup is the target's own prior: offsets equal absolute differences."""
    return sg.Evidence(track, source, setup, sim, prior=PRIOR)


def test_prior_only_is_low_and_returns_prior_values():
    r = sg.estimate_setup([], PRIOR)
    assert r["overall_confidence"] == "low"
    for key in ("wing_setup_0", "wing_setup_1", "arb_setup_0", "diff_onThrottle_setup", "brake_bias_setup"):
        e = r["setup"][key]
        assert e["source"] == "prior" and e["confidence"] == "low" and e["evidence"] == []
        assert e["value"] == pytest.approx(sg.snap(key, PRIOR[key]))
    assert r["first_test"]["key"] == "wing_setup_0" and "prior only" in r["first_test"]["text"]


def test_similar_track_dominates_distant_one():
    prior_fw = PRIOR["wing_setup_0"]
    close = ev("A", "baseline", 0.9, wing_setup_0=prior_fw + 10)
    far = ev("B", "baseline", 0.12, wing_setup_0=prior_fw - 10)
    r = sg.estimate_setup([close, far], PRIOR)["setup"]["wing_setup_0"]
    assert r["value"] > prior_fw + 4  # pulled to the close track, barely by the far one
    assert [i["track"] for i in r["evidence"]] == ["A", "B"]  # heaviest first
    low = sg.estimate_setup([far], PRIOR)["setup"]["wing_setup_0"]
    assert prior_fw - 10 < low["value"] <= prior_fw


def test_weak_evidence_ignored_below_min_similarity():
    r = sg.estimate_setup([ev("A", "baseline", 0.05, wing_setup_0=0)], PRIOR)["setup"]["wing_setup_0"]
    assert r["source"] == "prior" and r["evidence"] == []


def test_more_evidence_raises_confidence():
    def conf(n):
        evs = [ev(f"T{i}", "baseline", 0.8, wing_setup_0=30) for i in range(n)]
        return sg.estimate_setup(evs, PRIOR)["setup"]["wing_setup_0"]["confidence"]

    assert [conf(0), conf(1), conf(3)] == ["low", "medium", "high"]
    # similarity counts too: three very different tracks are worth less than one close one
    far = [ev(f"T{i}", "baseline", 0.2, wing_setup_0=30) for i in range(3)]
    assert sg.estimate_setup(far, PRIOR)["setup"]["wing_setup_0"]["confidence"] == "medium"


def test_source_weights_and_duplicate_setup_counted_once():
    same = [ev("A", "baseline", 0.8, wing_setup_0=33), ev("A", "duel", 0.8, wing_setup_0=33)]
    e = sg.estimate_setup(same, PRIOR)["setup"]["wing_setup_0"]
    assert len(e["evidence"]) == 1 and e["weight"] == pytest.approx(0.8)
    settled = sg.estimate_setup([ev("A", "settled", 0.8, wing_setup_0=33)], PRIOR)["setup"]["wing_setup_0"]
    assert settled["weight"] == pytest.approx(0.8 * sg.SOURCE_WEIGHTS["settled"])


def test_recency_discounts_old_evidence():
    now = datetime(2026, 10, 15, tzinfo=timezone.utc)
    assert sg.recency_factor("2026-10-15T00:00:00+00:00", now) == pytest.approx(1.0)
    assert sg.recency_factor("2020-01-01T00:00:00+00:00", now) == sg.RECENCY_FLOOR
    assert sg.recency_factor(None, now) == 1.0 and sg.recency_factor("garbage", now) == 1.0


def test_snapping_ranges_and_steps():
    wild = ev("A", "baseline", 1.0, wing_setup_0=500, brake_bias_setup=0.5719, diff_onThrottle_setup=-3,
              tyre_press_setup_0=psi_to_pa(26.123), tyre_press_setup_1=psi_to_pa(26.123))
    s = sg.estimate_setup([wild] * 20, PRIOR)["setup"]
    by_key = {p.key: p for p in SETUP_PARAMS}
    assert s["wing_setup_0"]["value"] <= 50  # a wild offset is clamped before snapping
    assert s["wing_setup_0"]["evidence"][0]["offset"] == pytest.approx(sg.OFFSET_CLAMP_FRAC * 50)
    assert 0.10 <= s["diff_onThrottle_setup"]["value"] < PRIOR["diff_onThrottle_setup"]
    assert s["brake_bias_setup"]["value"] == pytest.approx(0.57, abs=1e-9)
    p = by_key["tyre_press_setup_0"]
    steps = (s["tyre_press_setup_0"]["value"] - p.min_v) / p.step
    assert steps == pytest.approx(round(steps), abs=1e-6)
    for key, e in s.items():
        if key in by_key:
            assert by_key[key].min_v - 1e-6 <= e["value"] <= by_key[key].max_v + 1e-6


def test_left_right_mirrored():
    e = ev("A", "baseline", 0.9, susp_height_setup_0=20, susp_height_setup_1=24, tyre_press_setup_2=psi_to_pa(23))
    s = sg.estimate_setup([e], PRIOR)["setup"]
    assert s["susp_height_setup_0"]["value"] == s["susp_height_setup_1"]["value"]
    assert s["tyre_press_setup_2"]["value"] == s["tyre_press_setup_3"]["value"]
    assert s["susp_height_setup_0"]["evidence"][0]["value"] == pytest.approx(22)  # axle mean


def test_suspension_coherent_and_noted():
    crazy = [ev("A", "baseline", 1.0, susp_spring_setup_0=41, susp_spring_setup_1=3, arb_setup_0=1, arb_setup_1=21)] * 20
    s = sg.estimate_setup(crazy, PRIOR)["setup"]
    sf, sr = s["susp_spring_setup_0"]["value"], s["susp_spring_setup_1"]["value"]
    af, ar = s["arb_setup_0"]["value"], s["arb_setup_1"]["value"]
    assert 10 <= sf - sr <= 20 and abs(af - ar) <= 3
    assert any("note" in s[k] for k in ("susp_spring_setup_0", "susp_spring_setup_1", "arb_setup_0", "arb_setup_1"))


def test_camber_stays_at_meta_whatever_the_evidence():
    r = sg.estimate_setup([ev("A", "baseline", 1.0, camber_setup_0=-2.6, camber_setup_1=-1.2)] * 5, PRIOR)["setup"]
    for key, target in CAMBER_META.items():
        assert r[key]["value"] == pytest.approx(target) and r[key]["source"] == "meta" and r[key]["confidence"] == "high"


def test_overall_is_weakest_group_and_first_test_priority():
    aero_only = [ev(f"T{i}", "baseline", 0.9, wing_setup_0=30, wing_setup_1=25) for i in range(3)]
    r = sg.estimate_setup(aero_only, PRIOR)
    assert r["group_confidence"] == {"aero": "high", "mechanical": "low"} and r["overall_confidence"] == "low"
    assert r["first_test"]["key"] == "diff_onThrottle_setup"  # wings are high, next in priority is the diff
    full = sg.estimate_setup([ev(f"T{i}", "baseline", 0.9, **PRIOR) for i in range(4)], PRIOR)
    assert full["overall_confidence"] == "high"
    # an ARB is the least certain one: all else known
    known = {k: v for k, v in PRIOR.items() if not k.startswith("arb")}
    part = sg.estimate_setup([ev(f"T{i}", "baseline", 0.9, **known) for i in range(4)], PRIOR)
    assert part["first_test"]["key"] == "arb_setup_0" and part["first_test"]["label"] == "Front anti-roll bar"


def test_fuel_entry_added_when_given():
    r = sg.estimate_setup([], PRIOR, fuel_kg=34)["setup"]["fuel_setup"]
    assert r["value"] == 34 and r["source"] == "consumption"


def test_prior_for_every_catalogue_layout():
    for track in TRACK_LENGTHS_M:
        prior, src = sg.prior_for(track)
        assert "wing_setup_0" in prior and "fuel_setup" not in prior and src
    assert sg.prior_for("Zandvoort Reverse")[1] == "forward layout"
    assert sg.prior_for("Madring")[1] == "table median"


# ------------------------------------------------------------------ fuel


def test_fuel_own_measurement_times_half_race_plus_a_lap():
    f = sg.plan_fuel("Monza", {"Monza": [1.2, 1.1, 1.3, 1.2]})
    assert f["source"] == "measured on this track" and f["kg_per_lap"] == pytest.approx(1.2)
    assert f["race_kg"] == pytest.approx(math.ceil(1.2 * (race_laps("Monza") + 1)))
    assert f["quali_kg"] == sg.FUEL_MIN_KG == 5.0


def test_fuel_similar_tracks_then_library_then_default():
    samples = {"Hungaroring": [1.0] * 5, "Monaco": [0.9] * 5}
    km_h = 1.0 / (TRACK_LENGTHS_M["Hungaroring"] / 1000)
    sim = sg.plan_fuel("Spa", samples, {"Hungaroring": 0.8, "Monaco": 0.1})
    assert sim["source"] == "similar tracks"
    assert sim["kg_per_lap"] == pytest.approx(km_h * TRACK_LENGTHS_M["Spa"] / 1000, rel=1e-3)  # only the alike track counts
    assert sg.plan_fuel("Spa", samples, {"Hungaroring": 0.2})["source"] == "library kg/km"
    assert sg.plan_fuel("Spa", {})["source"] == "default kg/km"
    assert 5 <= sg.plan_fuel("Spa", {})["race_kg"] <= 110


def test_fuel_ignores_too_few_laps_on_own_track():
    assert sg.plan_fuel("Monza", {"Monza": [1.2, 1.2]})["source"] == "default kg/km"


def test_fuel_samples_from_library_clean_laps(tmp_root):
    with db.connect(tmp_root) as conn:
        conn.execute("INSERT INTO sessions (created_at, source_name, source_hash, track, telemetry_path) VALUES ('2026-01-01', 'a', 'h', 'Austria', 'x')")
        sid = conn.execute("SELECT id FROM sessions").fetchone()[0]
        rows = [(1, 70.0, 1.1), (2, 70.5, 1.2), (3, 70.2, 1.15), (4, 90.0, 0.7), (5, 70.1, -20.0), (6, 70.3, 9.0)]
        for lap, t, f in rows:
            conn.execute("INSERT INTO laps (session_id, lap, lap_time, fuel_used) VALUES (?, ?, ?, ?)", (sid, lap, t, f))
    got = sg.fuel_samples(tmp_root)
    assert sorted(got) == ["Spielberg"]  # alias normalised
    assert sorted(got["Spielberg"]) == [1.1, 1.15, 1.2]  # slow lap, refuel and pit artefacts dropped


# ------------------------------------------------------------------ transfer as an offset from the track's prior


def test_offset_transfers_not_absolute_value():
    """A high-wing track's baseline 3 above its own typical moves a low-wing target by +3, not toward 49."""
    target_prior = {**PRIOR, "wing_setup_0": 20.0}
    other_prior = {**PRIOR, "wing_setup_0": 46.0}
    evs = [sg.Evidence(f"Hung{i}", "baseline", {"wing_setup_0": 49.0}, 1.0, prior=other_prior) for i in range(6)]
    fw = sg.estimate_setup(evs, target_prior)["setup"]["wing_setup_0"]
    assert fw["value"] == pytest.approx(23, abs=0.6)
    item = fw["evidence"][0]
    assert item["offset"] == pytest.approx(3.0) and item["value"] == pytest.approx(23.0) and item["found"] == 49.0


def test_offset_is_clamped_to_a_share_of_the_range():
    target_prior = {**PRIOR, "wing_setup_0": 20.0}
    e = sg.Evidence("X", "baseline", {"wing_setup_0": 50.0}, 1.0, prior={**PRIOR, "wing_setup_0": 0.0})
    item = sg.estimate_setup([e], target_prior)["setup"]["wing_setup_0"]["evidence"][0]
    assert item["offset"] == pytest.approx(sg.OFFSET_CLAMP_FRAC * 50) and item["value"] == pytest.approx(20 + 25)


def test_track_without_prior_counts_absolute_only_when_very_similar():
    prior_fw = PRIOR["wing_setup_0"]
    far = sg.Evidence("Madring", "baseline", {"wing_setup_0": 5.0}, sg.ABSOLUTE_MIN_SIMILARITY - 0.05, prior=None)
    r = sg.estimate_setup([far], PRIOR)["setup"]["wing_setup_0"]
    assert r["source"] == "prior" and r["evidence"] == []
    close = [sg.Evidence(f"M{i}", "baseline", {"wing_setup_0": 0.0}, 0.9, prior=None) for i in range(5)]
    r = sg.estimate_setup(close, {**PRIOR, "wing_setup_0": 30.0})["setup"]["wing_setup_0"]
    assert r["evidence"][0]["value"] == 0.0 and r["evidence"][0]["offset"] is None and r["value"] < 12


def test_targets_own_evidence_stays_absolute():
    own = [sg.Evidence("Monza", "settled", {"wing_setup_0": 12.0 + i * 0}, 1.0, prior={**PRIOR, "wing_setup_0": 40.0}, own=True, name=str(i)) for i in range(1)]
    item = sg.estimate_setup(own, {**PRIOR, "wing_setup_0": 30.0})["setup"]["wing_setup_0"]
    assert item["evidence"][0]["value"] == 12.0 and item["evidence"][0]["offset"] is None and 12 < item["value"] < 30
