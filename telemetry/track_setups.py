"""
Baseline F1 26 garage setups by circuit (imported presets, see tools/import_setup_presets.py).

Ranges match the in-game garage UI:
- Fuel 5–110 kg
- Wings 0–50
- Diff on/off 10–100%
- Front camber −3.50…−2.50°, rear −2.00…−1.00°
- Front toe 0.00–0.20°, rear toe 0.10–0.25°
- Springs 1–41, ARB 1–21
- Front RH 15–35, rear RH 40–60
- Brake bias 50–70%, pressure 80–100%
- Front tyres 22.5–29.5 psi, rear 20.5–26.5 psi

SRT setup indices: 0/1 = front, 2/3 = rear (pressures / ride height).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .corners import normalize_track_name
from .setup_presets_data import PRESETS, SOURCE
from .setup_tweaker import psi_to_pa

_BASE: dict[str, float] = {
    "fuel_setup": 5.0,
    "wing_setup_0": 30.0,
    "wing_setup_1": 25.0,
    "diff_onThrottle_setup": 0.65,
    "diff_offThrottle_setup": 0.35,
    "camber_setup_0": -3.50,
    "camber_setup_1": -2.00,
    "toe_setup_0": 0.05,
    "toe_setup_1": 0.13,
    "susp_spring_setup_0": 37.0,
    "susp_spring_setup_1": 17.0,
    "arb_setup_0": 10.0,
    "arb_setup_1": 10.0,
    "susp_height_setup_0": 21.0,
    "susp_height_setup_1": 21.0,
    "susp_height_setup_2": 45.0,
    "susp_height_setup_3": 45.0,
    "brake_bias_setup": 0.57,
    "front_brake_bias": 0.57,
    "brake_press_setup": 0.95,
    "tyre_press_setup_0": psi_to_pa(26.5),
    "tyre_press_setup_1": psi_to_pa(26.5),
    "tyre_press_setup_2": psi_to_pa(23.5),
    "tyre_press_setup_3": psi_to_pa(23.5),
}


def np_clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def coherent_suspension(
    spring_f: float,
    spring_r: float,
    arb_f: float,
    arb_r: float,
) -> tuple[float, float, float, float]:
    """Keep springs and anti-roll bars inside the garage ranges (springs 1-41, ARB 1-21).

    No opinion about the front/rear split: the F1 26 meta runs packages like springs 41/4 and ARB 1/12, which a
    "real car" rule of thumb would wrongly call incoherent.
    """
    return (
        float(np_clip(spring_f, 1, 41)),
        float(np_clip(spring_r, 1, 41)),
        float(np_clip(arb_f, 1, 21)),
        float(np_clip(arb_r, 1, 21)),
    )


# Race fuel (kg) per track, kept from the earlier hand-written table; the generator plans fuel from measured laps.
FUEL_RACE_KG: dict[str, float] = {
    "Bahrain": 52, "Jeddah": 50, "Melbourne": 48, "Suzuka": 50, "Shanghai": 50, "Miami": 48, "Imola": 46,
    "Monaco": 40, "Montreal": 46, "Barcelona": 50, "Spielberg": 42, "Silverstone": 50, "Hungaroring": 44, "Spa": 52,
    "Zandvoort": 44, "Monza": 48, "Baku": 50, "Singapore": 48, "Austin": 50, "Mexico City": 46, "Interlagos": 46,
    "Las Vegas": 50, "Lusail": 50, "Yas Marina": 48,
}
FUEL_RACE_DEFAULT_KG = 50.0
FUEL_QUALI_KG = 5.0


def character_of(rear_wing: float) -> str:
    """Downforce character of a track from its baseline rear wing (used by the setup builder's wing rules)."""
    if rear_wing <= 10:
        return "low_drag"
    if rear_wing <= 20:
        return "medium_low"
    if rear_wing <= 30:
        return "medium"
    if rear_wing <= 40:
        return "medium_high"
    return "high_df"


def _pack(track: str, p: dict[str, Any]) -> dict[str, Any]:
    """One preset (``setup_presets_data.PRESETS`` row) as the quali / race garage dicts in SRT storage units.

    The preset is a race setup; quali differs only by fuel (parc fermé: same car for both).
    """
    fl, fr, rl, rr = (psi_to_pa(x) for x in p["psi"])
    race = deepcopy(_BASE)
    race.update(
        {
            "fuel_setup": float(FUEL_RACE_KG.get(track.removesuffix(" Reverse"), FUEL_RACE_DEFAULT_KG)),
            "wing_setup_0": float(p["fw"]),
            "wing_setup_1": float(p["rw"]),
            "diff_onThrottle_setup": float(p["diff_on"]),
            "diff_offThrottle_setup": float(p["diff_off"]),
            "camber_setup_0": float(p["camber_f"]),
            "camber_setup_1": float(p["camber_r"]),
            "toe_setup_0": float(p["toe_f"]),
            "toe_setup_1": float(p["toe_r"]),
            "susp_spring_setup_0": float(p["spring_f"]),
            "susp_spring_setup_1": float(p["spring_r"]),
            "arb_setup_0": float(p["arb_f"]),
            "arb_setup_1": float(p["arb_r"]),
            "susp_height_setup_0": float(p["ride_f"]),
            "susp_height_setup_1": float(p["ride_f"]),
            "susp_height_setup_2": float(p["ride_r"]),
            "susp_height_setup_3": float(p["ride_r"]),
            "brake_bias_setup": float(p["bias"]),
            "front_brake_bias": float(p["bias"]),
            "brake_press_setup": float(p["brake_press"]),
            "tyre_press_setup_0": fl,
            "tyre_press_setup_1": fr,
            "tyre_press_setup_2": rl,
            "tyre_press_setup_3": rr,
        }
    )
    quali = deepcopy(race)
    quali["fuel_setup"] = FUEL_QUALI_KG
    notes = f"{SOURCE['file']} · {SOURCE['sheet']} ({p['label']})"
    if p.get("strategy"):
        notes += f" · strategy: {p['strategy']}"
    return {"character": character_of(p["rw"]), "notes": notes, "quali": quali, "race": race}


# Baseline setup per catalogue track, from the imported presets (tools/import_setup_presets.py).
TRACK_TYPICAL_SETUPS: dict[str, dict[str, Any]] = {track: _pack(track, p) for track, p in PRESETS.items()}


def list_tracks_with_setups() -> list[str]:
    return sorted(TRACK_TYPICAL_SETUPS.keys())


def apply_weather_overlay(setup: dict[str, float], conditions: str | None = None) -> dict[str, float]:
    """
    Shift a dry typical toward damp / inter / wet garage targets.

    Pressures, wings, mechanical grip, and brake bias are the main levers.
    """
    from .conditions import STATE_LABELS, _as_state
    from .setup_tweaker import normalize_setup, psi_to_pa

    state = _as_state(conditions)
    out = normalize_setup(deepcopy(setup))
    if state == "dry":
        return out

    # Scale: damp mild → inter mid → wet strong
    scale = {"damp": 0.35, "inter": 0.7, "wet": 1.0}[state]
    wing_f = round(3 * scale)
    wing_r = round(6 * scale)  # plant the rear first in low grip
    press_f = -2.0 * scale
    press_r = -1.6 * scale
    arb_f = -round(2 * scale)
    arb_r = -round(2 * scale)
    spring_f = -round(2 * scale)
    spring_r = -round(2 * scale)
    # Tiny rearward only — big rearward + open off-throttle spins the car on light brake
    bias = -0.01 * scale
    ride_f = round(1 * scale)
    ride_r = round(2 * scale)
    # Keep off-throttle tighter than before (was −5% → entry snap)
    diff_off = -0.02 * scale
    brake_press = -0.03 * scale

    def bump(key: str, delta: float) -> None:
        if key in out:
            out[key] = float(out[key]) + delta

    bump("wing_setup_0", wing_f)
    bump("wing_setup_1", wing_r)
    bump("arb_setup_0", arb_f)
    bump("arb_setup_1", arb_r)
    bump("susp_spring_setup_0", spring_f)
    bump("susp_spring_setup_1", spring_r)
    # Re-harmonise after softens so wet doesn't recreate floppy-rear packs
    if all(k in out for k in ("susp_spring_setup_0", "susp_spring_setup_1", "arb_setup_0", "arb_setup_1")):
        sf, sr, af, ar = coherent_suspension(
            out["susp_spring_setup_0"],
            out["susp_spring_setup_1"],
            out["arb_setup_0"],
            out["arb_setup_1"],
        )
        out["susp_spring_setup_0"] = sf
        out["susp_spring_setup_1"] = sr
        out["arb_setup_0"] = af
        out["arb_setup_1"] = ar
    bump("brake_bias_setup", bias)
    if "front_brake_bias" in out:
        out["front_brake_bias"] = out.get("brake_bias_setup", out["front_brake_bias"])
    bump("brake_press_setup", brake_press)
    bump("susp_height_setup_0", ride_f)
    bump("susp_height_setup_1", ride_f)
    bump("susp_height_setup_2", ride_r)
    bump("susp_height_setup_3", ride_r)
    bump("diff_offThrottle_setup", diff_off)
    for k in ("tyre_press_setup_0", "tyre_press_setup_1"):
        bump(k, psi_to_pa(press_f))
    for k in ("tyre_press_setup_2", "tyre_press_setup_3"):
        bump(k, psi_to_pa(press_r))

    return normalize_setup(out)


def weather_notes(conditions: str | None = None) -> str:
    from .conditions import STATE_LABELS, _as_state

    state = _as_state(conditions)
    if state == "dry":
        return ""
    tips = {
        "damp": "Damp overlay: +rear wing, softer platform, mild pressure/brake-pressure drop.",
        "inter": "Inter overlay: plant rear with wing, softer ARB, lower tyre psi, slight rearward bias.",
        "wet": "Wet overlay: high rear DF, soft mech, lower tyre + brake pressure — keep bias stable.",
    }
    return tips[state]


def get_typical_setup(
    track: str | None,
    variant: str = "quali",
    conditions: str | None = None,
) -> dict[str, Any] | None:
    from .conditions import STATE_LABELS, _as_state

    key = normalize_track_name(track)
    if not key or key not in TRACK_TYPICAL_SETUPS:
        return None
    pack = TRACK_TYPICAL_SETUPS[key]
    variant = "race" if variant.lower().startswith("r") else "quali"
    setup = deepcopy(pack[variant])
    state = _as_state(conditions)
    notes = pack["notes"]
    if state != "dry":
        setup = apply_weather_overlay(setup, state)
        extra = weather_notes(state)
        notes = f"{notes} · {STATE_LABELS[state]}: {extra}"
    return {
        "track": key,
        "variant": variant,
        "character": pack["character"] if state == "dry" else f"{pack['character']}+{state}",
        "notes": notes,
        "setup": setup,
        "track_state": state,
    }
