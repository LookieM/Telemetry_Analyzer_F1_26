"""Imported baseline presets (tools/import_setup_presets.py -> telemetry/setup_presets_data.py)."""

import pytest

from telemetry.garage import to_garage
from telemetry.setup_tweaker import pa_to_psi
from telemetry.track_catalog import TRACK_LENGTHS_M
from telemetry.track_setups import TRACK_TYPICAL_SETUPS, coherent_suspension, get_typical_setup
from tools.import_setup_presets import parse_row


def test_every_catalogue_layout_has_a_preset():
    assert set(TRACK_LENGTHS_M) <= set(TRACK_TYPICAL_SETUPS)


def test_miami_preset_is_the_driven_safe_setup():
    s = to_garage(get_typical_setup("Miami", "race")["setup"])
    assert (s["wing_setup_0"], s["wing_setup_1"]) == (25, 20)
    assert (s["susp_spring_setup_0"], s["susp_spring_setup_1"], s["arb_setup_0"], s["arb_setup_1"]) == (38, 4, 6, 14)
    assert (s["susp_height_setup_0"], s["susp_height_setup_2"]) == (21, 48)
    q = get_typical_setup("Miami", "quali")["setup"]
    assert q["fuel_setup"] == 5 and q["wing_setup_1"] == 20  # same car, only fuel differs


def test_parse_row_garage_tyre_order_and_missing_slash():
    row = ["Las Vegas (USA)", "9 / 0", "100% / 20%", "-3.40 / -1.90 / 0.01 / 0.11", "37 / 8 / 7 / 8 / 23 / 48",
           "55% / 99%", "24.7 / 25.0 22.5 / 22.0", "", "M - H"]
    track, p = parse_row(row)
    assert track == "Las Vegas" and p["diff_off"] == pytest.approx(0.2) and p["bias"] == pytest.approx(0.55)
    assert p["psi"] == [25.0, 24.7, 22.0, 22.5]  # sheet FR / FL / RR / RL -> stored FL, FR, RL, RR
    assert p["strategy"] == "M - H"


def test_parse_row_rejects_wrong_shape():
    with pytest.raises(ValueError):
        parse_row(["Miami (USA)", "25", "100% / 20%", "-3.4 / -1.9 / 0.01 / 0.12", "38 / 4 / 6 / 14 / 21 / 48",
                   "56% / 99%", "26 / 26 / 22.7 / 22.7"])


def test_coherent_suspension_only_clamps_to_garage_ranges():
    assert coherent_suspension(41, 4, 1, 12) == (41, 4, 1, 12)
    assert coherent_suspension(45, 0, 0, 30) == (41, 1, 1, 21)


def test_preset_pressures_round_trip_psi():
    s = get_typical_setup("Barcelona", "race")["setup"]
    assert pa_to_psi(s["tyre_press_setup_0"]) == pytest.approx(28.2, abs=0.01)  # FL
    assert pa_to_psi(s["tyre_press_setup_1"]) == pytest.approx(26.3, abs=0.01)  # FR
