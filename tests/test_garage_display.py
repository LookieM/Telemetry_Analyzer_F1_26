from telemetry.garage_display import display_text, garage_display
from telemetry.setup_tweaker import psi_to_pa

SETUP = {"tyre_press_setup_0": psi_to_pa(25.5), "fuel_setup": 40.0, "brake_bias_setup": 0.56, "front_brake_bias": 0.56,
         "wing_setup_0": 25.0, "diff_onThrottle_setup": 0.65, "camber_setup_0": -3.5, "susp_height_setup_2": 50.0,
         "ballast_setup": 5.0, "bogus": 3.0}


def test_garage_order_units_and_hidden_keys():
    items = garage_display(SETUP)
    groups = [i["group"] for i in items]
    assert groups == sorted(groups, key=["Fuel", "Aero", "Transmission", "Geometry", "Suspension", "Brakes", "Tyres"].index)
    by = {i["key"]: i for i in items}
    assert "front_brake_bias" not in by and "bogus" not in by
    assert by["tyre_press_setup_0"]["value"] == 25.5 and by["tyre_press_setup_0"]["unit"] == "psi"
    assert by["diff_onThrottle_setup"]["value"] == 65 and by["diff_onThrottle_setup"]["unit"] == "%"
    assert by["brake_bias_setup"]["value"] == 56 and by["brake_bias_setup"]["unit"].startswith("%")
    assert by["camber_setup_0"]["value"] == -3.5 and by["camber_setup_0"]["unit"] == "°"
    assert by["fuel_setup"]["unit"] == "kg"


def test_text_lists_groups_and_units():
    text = display_text(garage_display(SETUP))
    assert text.splitlines()[0] == "Fuel" and "  Front wing: 25" in text and "  Diff on-throttle: 65%" in text
    assert "  Front left pressure: 25.5 psi" in text


def test_empty_setup():
    assert garage_display(None) == [] and display_text([]) == ""
