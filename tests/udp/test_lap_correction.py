"""Shared lap correction: synthetic laps in, asserts on the public functions only."""

import math

import pytest

from telemetria_server.live.engineer import EngineerLap
from telemetria_server.live.lap_correction import (DEFAULT_DEG, MISTAKE_S, NOISE_FLOOR, Lap, correct_groups,
                                                   estimate_degradation, fuel_fix, noise_estimate,
                                                   representative_laps)


def lap(n, t, **kw):
    return Lap(lap=n, lap_time_s=t, **kw)


def test_engineer_lap_is_the_shared_lap():
    assert EngineerLap is Lap


def test_lap_flying_and_fuel_mid():
    assert lap(1, 90.0).flying
    assert not lap(1, 90.0, valid=False).flying
    assert not lap(1, 90.0, out_lap=True).flying
    assert lap(1, 90.0, fuel_start=10, fuel_end=8).fuel_mid == 9.0
    assert lap(1, 90.0, fuel_start=10).fuel_mid is None


def test_representative_laps_drops_mistakes_only():
    laps = [lap(1, 90.0), lap(2, 90.2), lap(3, 90.1), lap(4, 90.0 + MISTAKE_S + 0.5)]
    assert [x.lap for x in representative_laps(laps)] == [1, 2, 3]
    assert representative_laps([]) == []
    assert len(representative_laps([lap(1, 90.0), lap(2, 90.0 + MISTAKE_S)])) == 2


def test_fuel_fix_scales_with_fuel_above_reference():
    assert fuel_fix(lap(1, 90.0, fuel_start=12, fuel_end=10), 9.0, 0.05) == pytest.approx(0.1)
    assert fuel_fix(lap(1, 90.0), 9.0, 0.05) == 0.0


def test_degradation_sources():
    fuelless = lambda x: 0.0
    few = [lap(i, 90.0, tyre_age_laps=i, compound=18, tyre_set_idx=1) for i in range(3)]
    assert estimate_degradation(few, fuelless) == (DEFAULT_DEG, "default")
    assert estimate_degradation(few, fuelless, {18: 0.07}) == (0.07, "compound")
    many = [lap(i, 90.0 + 0.2 * i, tyre_age_laps=i, compound=18, tyre_set_idx=1) for i in range(5)]
    deg, src = estimate_degradation(many, fuelless, {18: 0.07})
    assert src == "fitted" and deg == pytest.approx(0.2)
    faster = [lap(i, 90.0 - 0.2 * i, tyre_age_laps=i, tyre_set_idx=1) for i in range(5)]
    assert estimate_degradation(faster, fuelless)[0] == 0.0  # clamped at zero


def test_correct_groups_removes_fuel_and_age():
    # same true pace; group "b" carries 2 kg more fuel (0.05 s/kg) and is 2 laps older (0.1 s/lap)
    a = [lap(i, 90.0, fuel_start=10, fuel_end=10, tyre_age_laps=3, s1=30.0, s2=30.0, s3=30.0) for i in range(2)]
    b = [lap(i, 90.3, fuel_start=12, fuel_end=12, tyre_age_laps=5, s1=30.1, s2=30.1, s3=30.1) for i in range(2)]
    c = correct_groups({"a": a, "b": b}, 0.05, {})
    assert c.deg_source == "default" and c.deg_s_per_lap == DEFAULT_DEG
    m = c.means
    assert m["a"] == pytest.approx(m["b"]) and m["a"] == pytest.approx(90.15)
    assert c.sectors["b"][0][0] == pytest.approx(30.1 - 0.15 * 30.1 / 90.3)


def test_correct_groups_missing_sector_is_nan_and_any_keys():
    c = correct_groups({"x": [lap(1, 90.0)], "y": [lap(2, 91.0, s1=30.0)], "z": [lap(3, 92.0)]}, 0.03)
    assert set(c.times) == {"x", "y", "z"}
    assert math.isnan(c.sectors["x"][0][0]) and not math.isnan(c.sectors["y"][0][0])


def test_noise_floor_and_spread():
    assert noise_estimate({"1": [90.0, 90.0], "2": [90.1, 90.1]}) == NOISE_FLOOR
    assert noise_estimate({"1": [90.0]}) == NOISE_FLOOR
    wide = noise_estimate({"1": [90.0, 91.0], "2": [90.0, 91.0]})
    assert wide == pytest.approx(math.sqrt(0.5))
