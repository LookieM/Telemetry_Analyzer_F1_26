"""
Typical F1 26 garage baselines by circuit.

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
    """
    Keep spring/ARB packages driveable.

    Front-stiff / rear-floppy (e.g. 41/3 springs + ARB 1/15) produces cartoon
    understeer then sudden oversteer. Keep a normal F–R spring split and ARBs
    within a few clicks of each other.
    """
    sf = np_clip(spring_f, 30, 40)
    sr = np_clip(spring_r, 12, 22)
    split = sf - sr
    if split > 20:
        sr = np_clip(sf - 18, 12, 22)
    elif split < 10:
        sr = np_clip(sf - 14, 12, 22)
        if sf - sr < 10:
            sf = np_clip(sr + 14, 30, 40)

    af = np_clip(arb_f, 7, 15)
    ar = np_clip(arb_r, 7, 15)
    if abs(af - ar) > 3:
        mid = round((af + ar) / 2)
        if arb_f >= arb_r:
            af, ar = float(np_clip(mid + 1, 7, 15)), float(np_clip(mid - 1, 7, 15))
        else:
            af, ar = float(np_clip(mid - 1, 7, 15)), float(np_clip(mid + 1, 7, 15))
    return float(sf), float(sr), float(af), float(ar)


def _pack(
    *,
    fw: float,
    rw: float,
    notes: str,
    fuel_quali: float = 5.0,
    fuel_race: float = 55.0,
    spring_f: float = 37.0,
    spring_r: float = 17.0,
    arb_f: float = 10.0,
    arb_r: float = 10.0,
    bias: float = 0.57,
    brake_press: float = 0.95,
    press_f: float = 25.0,
    press_r: float = 21.5,
    ride_f: float = 21.0,
    ride_r: float = 45.0,
    diff_on: float = 0.65,
    diff_off: float = 0.35,
    camber_f: float = -3.50,
    camber_r: float = -2.00,
    toe_f: float = 0.05,
    toe_r: float = 0.13,
    character: str = "balanced",
) -> dict[str, Any]:
    """press_* in psi; ride_f 15–35, ride_r 40–60."""
    ride_f = float(np_clip(ride_f, 15, 35))
    ride_r = float(np_clip(ride_r, 40, 60))
    fuel_quali = float(np_clip(fuel_quali, 5, 110))
    fuel_race = float(np_clip(fuel_race, 5, 110))
    spring_f, spring_r, arb_f, arb_r = coherent_suspension(spring_f, spring_r, arb_f, arb_r)
    pf = psi_to_pa(press_f)
    pr = psi_to_pa(press_r)
    quali = deepcopy(_BASE)
    quali.update(
        {
            "fuel_setup": fuel_quali,
            "wing_setup_0": float(fw),
            "wing_setup_1": float(rw),
            "diff_onThrottle_setup": float(diff_on),
            "diff_offThrottle_setup": float(diff_off),
            "camber_setup_0": float(camber_f),
            "camber_setup_1": float(camber_r),
            "toe_setup_0": float(toe_f),
            "toe_setup_1": float(toe_r),
            "susp_spring_setup_0": float(spring_f),
            "susp_spring_setup_1": float(spring_r),
            "arb_setup_0": float(arb_f),
            "arb_setup_1": float(arb_r),
            "susp_height_setup_0": ride_f,
            "susp_height_setup_1": ride_f,
            "susp_height_setup_2": ride_r,
            "susp_height_setup_3": ride_r,
            "brake_bias_setup": float(bias),
            "front_brake_bias": float(bias),
            "brake_press_setup": float(brake_press),
            "tyre_press_setup_0": pf,
            "tyre_press_setup_1": pf,
            "tyre_press_setup_2": pr,
            "tyre_press_setup_3": pr,
        }
    )
    race = deepcopy(quali)
    race["wing_setup_1"] = min(50.0, rw + 1.0)
    race["diff_onThrottle_setup"] = min(1.0, diff_on + 0.05)
    race["fuel_setup"] = fuel_race
    race["tyre_press_setup_0"] = psi_to_pa(min(29.5, press_f + 0.3))
    race["tyre_press_setup_1"] = psi_to_pa(min(29.5, press_f + 0.3))
    race["tyre_press_setup_2"] = psi_to_pa(min(26.5, press_r + 0.3))
    race["tyre_press_setup_3"] = psi_to_pa(min(26.5, press_r + 0.3))
    return {
        "character": character,
        "notes": notes,
        "quali": quali,
        "race": race,
    }


TRACK_TYPICAL_SETUPS: dict[str, dict[str, Any]] = {
    "Bahrain": _pack(
        fw=44, rw=25, character="medium",
        notes="Medium DF desert track — firm front spring, ARB 12/10, RH 20/44.",
        spring_f=37, spring_r=19, arb_f=12, arb_r=10, bias=0.56, fuel_race=52,
        press_f=25.0, press_r=21.4, ride_f=20, ride_r=44,
        diff_on=1.0, diff_off=0.45, toe_f=0.00, toe_r=0.10,
    ),
    "Jeddah": _pack(
        fw=22, rw=18, character="low_drag",
        notes="High-speed street circuit — prioritise top speed, keep rear for blind kinks.",
        spring_f=38, spring_r=14, arb_f=11, arb_r=12, bias=0.56, fuel_race=50,
        press_f=26.0, press_r=22.0, ride_f=22, ride_r=48,
        diff_on=0.95, diff_off=0.35,
    ),
    "Melbourne": _pack(
        fw=32, rw=28, character="medium",
        notes="Stop-go street layout — braking stability and rotation for 90° corners.",
        spring_f=36, spring_r=16, arb_f=11, arb_r=10, bias=0.56, fuel_race=48,
        press_f=24.5, press_r=21.5, ride_f=22, ride_r=48,
        diff_on=0.80, diff_off=0.35,
    ),
    "Suzuka": _pack(
        fw=34, rw=28, character="high_df",
        notes="High-speed flowing corners — aero platform through Esses / 130R.",
        spring_f=38, spring_r=15, arb_f=10, arb_r=12, bias=0.56, fuel_race=50,
        press_f=25.5, press_r=22.0, ride_f=22, ride_r=47,
        diff_on=0.90, diff_off=0.40,
    ),
    "Shanghai": _pack(
        fw=30, rw=26, character="medium",
        notes="Long T1–T3 + hairpin — front for the snake, traction for T14.",
        spring_f=37, spring_r=16, arb_f=12, arb_r=10, bias=0.56, fuel_race=50,
        press_f=25.0, press_r=21.5, ride_f=22, ride_r=48,
    ),
    "Miami": _pack(
        fw=30, rw=25, character="medium",
        notes="From in-game Miami SQ baseline — springs 37/17, ARB 10/10, RH 21/45, 26.5/23.5 psi.",
        spring_f=37, spring_r=17, arb_f=10, arb_r=10, bias=0.55, fuel_race=48,
        press_f=26.5, press_r=23.5, ride_f=21, ride_r=45,
        diff_on=0.65, diff_off=0.35,
        camber_f=-3.50, camber_r=-2.00, toe_f=0.04, toe_r=0.13,
    ),
    "Imola": _pack(
        fw=33, rw=28, character="medium_high",
        notes="Kerbs and direction changes — slightly higher DF, compliant ride.",
        spring_f=35, spring_r=14, arb_f=10, arb_r=10, bias=0.55, fuel_race=46,
        press_f=24.5, press_r=21.5, ride_f=23, ride_r=50,
        diff_on=0.80, diff_off=0.35,
    ),
    "Monaco": _pack(
        fw=50, rw=50, character="high_df",
        notes="Max DF street — soft-but-matched ARBs, compliant rear (not floppy).",
        spring_f=36, spring_r=16, arb_f=8, arb_r=8, bias=0.56, fuel_race=40,
        press_f=23.45, press_r=20.5, ride_f=23, ride_r=51,
        diff_on=0.75, diff_off=0.28, toe_f=0.00, toe_r=0.10,
    ),
    "Montreal": _pack(
        fw=26, rw=22, character="medium_low",
        notes="Heavy braking + walls — strong bite, decent straight speed.",
        spring_f=38, spring_r=14, arb_f=12, arb_r=11, bias=0.57, fuel_race=46,
        press_f=26.0, press_r=22.0, ride_f=22, ride_r=48,
        diff_on=0.90, diff_off=0.35,
    ),
    "Barcelona": _pack(
        fw=35, rw=30, character="high_df",
        notes="Aero test track — higher DF, stable mid-corner through T3/T9.",
        spring_f=38, spring_r=15, arb_f=11, arb_r=12, bias=0.56, fuel_race=50,
        press_f=25.0, press_r=21.8, ride_f=22, ride_r=47,
        diff_on=0.90, diff_off=0.40,
    ),
    "Spielberg": _pack(
        fw=28, rw=24, character="medium_low",
        notes="Short lap, big stops — bias and traction matter more than peak DF.",
        spring_f=37, spring_r=15, arb_f=12, arb_r=10, bias=0.56, fuel_race=42,
        press_f=25.5, press_r=21.5, ride_f=21, ride_r=46,
        diff_on=0.95, diff_off=0.40,
    ),
    "Silverstone": _pack(
        fw=32, rw=28, character="medium_high",
        notes="Fast direction changes — Maggotts/Becketts need aero + rear support.",
        spring_f=38, spring_r=15, arb_f=10, arb_r=12, bias=0.56, fuel_race=50,
        press_f=25.5, press_r=22.0, ride_f=22, ride_r=47,
        diff_on=0.90, diff_off=0.40,
    ),
    "Hungaroring": _pack(
        fw=42, rw=40, character="high_df",
        notes="Twisty permanent track — high DF, matched softish platform for traction.",
        spring_f=35, spring_r=16, arb_f=9, arb_r=9, bias=0.56, fuel_race=44,
        press_f=24.0, press_r=21.0, ride_f=23, ride_r=50,
        diff_on=0.70, diff_off=0.30,
    ),
    "Spa": _pack(
        fw=20, rw=8, character="low_drag",
        notes="Eau Rouge + Kemmel — low drag with a coherent firm platform (not split ARBs).",
        spring_f=38, spring_r=16, arb_f=10, arb_r=11, bias=0.57, fuel_race=52,
        press_f=26.65, press_r=21.5, ride_f=23, ride_r=48,
        diff_on=1.0, diff_off=0.30, toe_f=0.00, toe_r=0.10,
    ),
    "Zandvoort": _pack(
        fw=38, rw=36, character="high_df",
        notes="Banked corners — high DF, careful pressures, strong front axle.",
        spring_f=37, spring_r=15, arb_f=10, arb_r=10, bias=0.56, fuel_race=44,
        press_f=24.5, press_r=21.2, ride_f=23, ride_r=50,
        diff_on=0.80, diff_off=0.35,
    ),
    "Monza": _pack(
        fw=11, rw=4, character="low_drag",
        notes="Temple of speed — low wing, firm but matched springs/ARBs (no 41/3 chaos).",
        spring_f=39, spring_r=18, arb_f=11, arb_r=12, bias=0.57, fuel_race=48,
        press_f=28.5, press_r=24.5, ride_f=23, ride_r=48,
        diff_on=0.90, diff_off=0.30, toe_f=0.00, toe_r=0.10,
    ),
    "Baku": _pack(
        fw=18, rw=14, character="low_drag",
        notes="Long straight + castle section — low drag, rotation for street 90°s.",
        spring_f=38, spring_r=16, arb_f=10, arb_r=11, bias=0.57, fuel_race=50,
        press_f=27.0, press_r=23.0, ride_f=22, ride_r=48,
        diff_on=0.90, diff_off=0.30,
    ),
    "Singapore": _pack(
        fw=45, rw=42, character="high_df",
        notes="Night street marathon — high DF, soft matched platform.",
        spring_f=34, spring_r=15, arb_f=8, arb_r=8, bias=0.56, fuel_race=48,
        press_f=23.5, press_r=20.8, ride_f=24, ride_r=52,
        diff_on=0.70, diff_off=0.28,
    ),
    "Austin": _pack(
        fw=32, rw=28, character="medium",
        notes="COTA Esses + stadium — aero for T1–T6, traction for T11–T15.",
        spring_f=37, spring_r=15, arb_f=11, arb_r=11, bias=0.56, fuel_race=50,
        press_f=25.0, press_r=21.8, ride_f=22, ride_r=48,
    ),
    "Mexico City": _pack(
        fw=38, rw=34, character="high_df",
        notes="Altitude / thin air — run more wing than sea-level tracks of similar layout.",
        spring_f=36, spring_r=14, arb_f=10, arb_r=10, bias=0.56, fuel_race=46,
        press_f=24.5, press_r=21.5, ride_f=23, ride_r=49,
        diff_on=0.85, diff_off=0.40,
    ),
    "Interlagos": _pack(
        fw=30, rw=26, character="medium",
        notes="S do Senna + bumpy — responsive front, compliant ride, mixed DF.",
        spring_f=35, spring_r=14, arb_f=11, arb_r=10, bias=0.56, fuel_race=46,
        press_f=25.0, press_r=21.5, ride_f=23, ride_r=50,
        diff_on=0.85, diff_off=0.35,
    ),
    "Las Vegas": _pack(
        fw=16, rw=10, character="low_drag",
        notes="Strip straights — strip wing, strong cooling, stable high-speed rear.",
        spring_f=39, spring_r=12, arb_f=10, arb_r=13, bias=0.57, fuel_race=50,
        press_f=28.0, press_r=24.0, ride_f=22, ride_r=47,
        diff_on=0.95, diff_off=0.35,
    ),
    "Lusail": _pack(
        fw=30, rw=26, character="medium",
        notes="Fast flowing desert lap — medium DF, watch rear temps.",
        spring_f=37, spring_r=15, arb_f=11, arb_r=11, bias=0.56, fuel_race=50,
        press_f=25.5, press_r=22.0, ride_f=22, ride_r=48,
    ),
    "Yas Marina": _pack(
        fw=30, rw=26, character="medium",
        notes="Technical sector 2–3 — balance straight speed with hotel-section rotation.",
        spring_f=37, spring_r=16, arb_f=11, arb_r=10, bias=0.56, fuel_race=48,
        press_f=25.0, press_r=21.5, ride_f=22, ride_r=48,
    ),
}


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
