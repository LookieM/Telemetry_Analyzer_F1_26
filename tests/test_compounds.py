"""Compound codes, S/M/H inference and the per-track allocation override."""

from __future__ import annotations

import pandas as pd

from telemetry.channels import inventory, primary_tyre_temp, wheel_columns
from telemetry.compounds import c_label, clear_allocation, get_allocation, roles_from_codes, set_allocation
from telemetry.db import compact_dataframe


def test_actual_compound_codes_map_to_c_numbers():
    assert [c_label(c) for c in (22, 16, 17, 18, 19, 20, 21)] == ["C6", "C5", "C4", "C3", "C2", "C1", "C0"]
    assert c_label(7) == "Inter" and c_label(8) == "Wet"
    assert c_label(-1) == "—" and c_label(None) == "—"


def test_roles_softest_first_and_gap_fills_the_medium():
    assert roles_from_codes([18, 19, 20]) == {18: "S", 19: "M", 20: "H"}
    assert roles_from_codes([16, 18, 8]) == {16: "S", 17: "M", 18: "H"}  # C5 + C3 seen: C4 is the medium
    assert roles_from_codes([22, 16, 8]) == {22: "S", 16: "M", 17: "H"}  # C6 + C5: nothing softer than C6, C4 is the hard
    assert roles_from_codes([18, 19]) == {18: "S", 19: "M"}  # an ordinary adjacent pair: softest is the soft
    assert roles_from_codes([7, 8]) == {}


def test_manual_allocation_overrides_and_clears(tmp_root):
    set_allocation("Catalunya", 17, 18, 19, app_root=tmp_root)
    alloc = get_allocation("Barcelona", tmp_root)  # alias resolves to the same track
    assert alloc.source == "manual" and alloc.role(17) == "S" and alloc.role(19) == "H"
    assert alloc.label(18) == "C3 (M)" and alloc.label(7) == "Inter"
    clear_allocation("Barcelona", tmp_root)
    # empty library: nothing to infer, so the provisional 2026 Pirelli nomination (C4/C3/C2) shows
    fallback = get_allocation("Barcelona", tmp_root)
    assert fallback.source == "pirelli-2026" and fallback.roles == {17: "S", 18: "M", 19: "H"}


def test_compact_keeps_every_numeric_channel_including_constant_ones():
    df = pd.DataFrame(
        {
            "lap": [0, 0, 1],
            "speed": [100.0, 200.0, 150.0],
            "brakes_temperature_0": [300.0, 450.0, 500.0],  # unknown to the core set -> kept
            "weather": [2, 2, 2],  # constant for the session, still information -> kept
            "pitStopTime": [0.0, 0.0, 0.0],
            "label": ["a", "b", "c"],  # text -> dropped
        }
    )
    out = compact_dataframe(df)
    assert {"brakes_temperature_0", "weather", "pitStopTime", "speed"} <= set(out.columns)
    assert "label" not in out.columns
    assert out["brakes_temperature_0"].dtype == "float32"


def test_channel_registry_resolves_aliases_and_prefers_inner_temperature():
    df = pd.DataFrame({f"tyres_inner_temperature_{i}": [90.0] for i in range(4)} | {f"tyre_temp_{i}": [80.0] for i in range(4)})
    assert wheel_columns(df, "tyre_inner_temp") == [f"tyres_inner_temperature_{i}" for i in range(4)]
    label, cols = primary_tyre_temp(df)
    assert label == "Tyre inner temp" and cols[0] == "tyres_inner_temperature_0"
    df2 = pd.DataFrame({f"brakeTemp{i}": [400.0] for i in range(4)} | {"mystery": [1.0]})
    assert wheel_columns(df2, "brake_temp") == [f"brakeTemp{i}" for i in range(4)]
    inv = inventory(df2)
    assert "Brake temp" in set(inv["Channel"]) and "mystery" in set(inv["Channel"])


def test_c6_pair_implies_the_harder_third_compound():
    from telemetry.compounds import roles_from_codes

    assert roles_from_codes([22, 16]) == {22: "S", 16: "M", 17: "H"}  # Montreal in the game: C6/C5 seen -> C4 hard
    assert roles_from_codes([17, 18]) == {17: "S", 18: "M"}  # an ordinary adjacent pair stays open
