"""
Setup tweaker with heuristic lap-time estimates.

Parameter limits match the F1 26 in-game garage (verified from setup UI):
Fuel, Aero, Transmission, Geometry, Suspension, Brakes, Tyres.

SRT stores tyre pressures in Pascals; the UI shows psi.
Setup wheel indices in SRT: 0/1 = front, 2/3 = rear (pressures / ride height).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .metrics import FUEL_S_PER_KG

# F1 26 / SRT: pressures stored as Pa; garage UI uses psi
PA_PER_PSI = 6894.757
PSI_SCALE = 1.0 / PA_PER_PSI


def psi_to_pa(psi: float) -> float:
    return float(psi) * PA_PER_PSI


def pa_to_psi(pa: float) -> float:
    return float(pa) * PSI_SCALE


@dataclass
class SetupParam:
    key: str
    label: str
    group: str
    unit: str
    min_v: float
    max_v: float
    step: float
    # Seconds of lap time per +1 unit (negative = faster when increased)
    dt_per_unit: float
    notes: str = ""
    display_scale: float = 1.0  # multiply stored value for UI (Pa -> psi, frac -> %)


# Exact F1 26 garage ranges from in-game setup screens.
SETUP_PARAMS: list[SetupParam] = [
    # --- Fuel ---
    SetupParam(
        "fuel_setup",
        "Fuel load",
        "Fuel",
        "kg",
        5,
        110,
        1,
        0.030,
        "Garage range 5–110 kg. Full tank costs ~3 s/lap vs minimum.",
    ),
    # --- Aerodynamics ---
    SetupParam("wing_setup_0", "Front wing", "Aero", "", 0, 50, 1, -0.012, "More FW → better front grip, more drag. Range 0–50."),
    SetupParam("wing_setup_1", "Rear wing", "Aero", "", 0, 50, 1, -0.008, "More RW → traction/stability, more drag. Range 0–50."),
    # --- Transmission ---
    SetupParam(
        "diff_onThrottle_setup",
        "Diff on-throttle",
        "Transmission",
        "%",
        0.10,
        1.0,
        0.01,
        0.010,
        "Unlocked 10% → Locked 100%. Higher → more exit stability / understeer.",
        display_scale=100.0,
    ),
    SetupParam(
        "diff_offThrottle_setup",
        "Diff off-throttle",
        "Transmission",
        "%",
        0.10,
        1.0,
        0.01,
        0.008,
        "Unlocked 10% → Locked 100%. Higher → more entry stability, less rotation.",
        display_scale=100.0,
    ),
    # --- Suspension geometry ---
    SetupParam(
        "camber_setup_0",
        "Front camber",
        "Geometry",
        "°",
        -3.50,
        -2.50,
        0.01,
        0.05,
        "More negative → better mid-corner grip (F1 26 meta: run −3.50°). Range −3.50 to −2.50°.",
    ),
    SetupParam(
        "camber_setup_1",
        "Rear camber",
        "Geometry",
        "°",
        -2.00,
        -1.00,
        0.01,
        0.04,
        "More negative → rear grip (F1 26 meta: run −2.00°). Range −2.00 to −1.00°.",
    ),
    SetupParam(
        "toe_setup_0",
        "Front toe",
        "Geometry",
        "°",
        0.00,
        0.20,
        0.01,
        0.08,
        "Toe-out helps turn-in; costs straight-line feel. Range 0.00–0.20°.",
    ),
    SetupParam(
        "toe_setup_1",
        "Rear toe",
        "Geometry",
        "°",
        0.10,
        0.25,
        0.01,
        0.06,
        "More toe-in → stability; less → rotation. Range 0.10–0.25°.",
    ),
    # --- Suspension ---
    SetupParam(
        "susp_spring_setup_0",
        "Front suspension",
        "Suspension",
        "",
        1,
        41,
        1,
        0.003,
        "Soft 1 → Hard 41. Stiffer → aero platform, harsher over bumps.",
    ),
    SetupParam(
        "susp_spring_setup_1",
        "Rear suspension",
        "Suspension",
        "",
        1,
        41,
        1,
        0.003,
        "Soft 1 → Hard 41. Softer rear often helps traction.",
    ),
    SetupParam(
        "arb_setup_0",
        "Front anti-roll bar",
        "Suspension",
        "",
        1,
        21,
        1,
        0.004,
        "Soft 1 → Hard 21. Stiffer front → sharper in, less mid-corner rotation.",
    ),
    SetupParam(
        "arb_setup_1",
        "Rear anti-roll bar",
        "Suspension",
        "",
        1,
        21,
        1,
        0.003,
        "Soft 1 → Hard 21. Stiffer rear → more rotation, less rear grip.",
    ),
    # SRT may export L/R; garage UI is one front / one rear value (keep sides equal).
    SetupParam("susp_height_setup_0", "Front ride height L", "Suspension", "", 15, 35, 1, 0.006, "Front ride height. Garage range 15–35."),
    SetupParam("susp_height_setup_1", "Front ride height R", "Suspension", "", 15, 35, 1, 0.006, "Front ride height. Garage range 15–35."),
    SetupParam("susp_height_setup_2", "Rear ride height L", "Suspension", "", 40, 60, 1, 0.005, "Rear ride height. Garage range 40–60."),
    SetupParam("susp_height_setup_3", "Rear ride height R", "Suspension", "", 40, 60, 1, 0.005, "Rear ride height. Garage range 40–60."),
    # --- Brakes ---
    SetupParam(
        "brake_bias_setup",
        "Brake bias",
        "Brakes",
        "% front",
        0.50,
        0.70,
        0.01,
        0.020,
        "50–70% front. Prefer ~57%+ for stability; too rearward locks the rear on light brake.",
        display_scale=100.0,
    ),
    SetupParam(
        "front_brake_bias",
        "Brake bias (live)",
        "Brakes",
        "% front",
        0.50,
        0.70,
        0.01,
        0.020,
        "Live mirror of front brake bias if present in telemetry.",
        display_scale=100.0,
    ),
    SetupParam(
        "brake_press_setup",
        "Brake pressure",
        "Brakes",
        "%",
        0.80,
        1.0,
        0.01,
        -0.015,
        "Min 80% – Max 100%. Higher → stronger initial bite.",
        display_scale=100.0,
    ),
    # --- Tyres (psi in garage; Pa in SRT) ---
    SetupParam(
        "tyre_press_setup_0",
        "Front left pressure",
        "Tyres",
        "psi",
        psi_to_pa(22.5),
        psi_to_pa(29.5),
        psi_to_pa(0.05),
        0.0,
        "Front tyre pressure. Range 22.5–29.5 psi.",
        display_scale=PSI_SCALE,
    ),
    SetupParam(
        "tyre_press_setup_1",
        "Front right pressure",
        "Tyres",
        "psi",
        psi_to_pa(22.5),
        psi_to_pa(29.5),
        psi_to_pa(0.05),
        0.0,
        "Front tyre pressure. Range 22.5–29.5 psi.",
        display_scale=PSI_SCALE,
    ),
    SetupParam(
        "tyre_press_setup_2",
        "Rear left pressure",
        "Tyres",
        "psi",
        psi_to_pa(20.5),
        psi_to_pa(26.5),
        psi_to_pa(0.05),
        0.0,
        "Rear tyre pressure. Range 20.5–26.5 psi.",
        display_scale=PSI_SCALE,
    ),
    SetupParam(
        "tyre_press_setup_3",
        "Rear right pressure",
        "Tyres",
        "psi",
        psi_to_pa(20.5),
        psi_to_pa(26.5),
        psi_to_pa(0.05),
        0.0,
        "Rear tyre pressure. Range 20.5–26.5 psi.",
        display_scale=PSI_SCALE,
    ),
]


@dataclass
class SetupDeltaLine:
    key: str
    label: str
    baseline: float
    proposed: float
    delta_units: float
    est_dt: float
    note: str


@dataclass
class SetupEstimate:
    baseline: dict[str, float]
    proposed: dict[str, float]
    lines: list[SetupDeltaLine]
    total_dt: float
    aero_balance_note: str
    confidence: str
    breakdown: dict[str, float] = field(default_factory=dict)


def _param_map() -> dict[str, SetupParam]:
    return {p.key: p for p in SETUP_PARAMS}


def _coerce_setup_units(raw: dict[str, Any]) -> dict[str, Any]:
    """Map SRT fractional exports (0–1) to in-game garage units where needed."""
    out = dict(raw)
    pmap = _param_map()
    fw, rw = out.get("wing_setup_0"), out.get("wing_setup_1")
    try:
        fw_f = float(fw) if fw is not None else None
        rw_f = float(rw) if rw is not None else None
    except (TypeError, ValueError):
        fw_f = rw_f = None
    if fw_f is not None and rw_f is not None:
        mx = max(abs(fw_f), abs(rw_f))
        # Some exports store max wing as 1.0 instead of 50 clicks
        if 0 < mx <= 1.05:
            out["wing_setup_0"] = fw_f * 50.0
            out["wing_setup_1"] = rw_f * 50.0

    percent_keys = (
        "brake_bias_setup",
        "front_brake_bias",
        "brake_press_setup",
        "diff_onThrottle_setup",
        "diff_offThrottle_setup",
    )
    for key in percent_keys:
        if key not in out or out[key] is None:
            continue
        try:
            val = float(out[key])
        except (TypeError, ValueError):
            continue
        p = pmap.get(key.replace("front_brake_bias", "brake_bias_setup"))
        if p is None and key == "front_brake_bias":
            p = pmap.get("brake_bias_setup")
        if p is None:
            continue
        # Exports often store 57 / 65 / 95 instead of 0.57 / 0.65 / 0.95
        if val > p.max_v + 1e-6 and val <= p.max_v * p.display_scale + 1e-6:
            out[key] = val / p.display_scale
    return out


def normalize_setup(raw: dict[str, Any]) -> dict[str, float]:
    raw = _coerce_setup_units(raw or {})
    out: dict[str, float] = {}
    for p in SETUP_PARAMS:
        if p.key in raw and raw[p.key] is not None:
            try:
                out[p.key] = float(np.clip(float(raw[p.key]), p.min_v, p.max_v))
            except (TypeError, ValueError):
                continue
    return out


def display_value(param: SetupParam, value: float) -> float:
    return float(value) * param.display_scale


def storage_value(param: SetupParam, display: float) -> float:
    return float(display) / param.display_scale if param.display_scale else float(display)


def estimate_setup_delta(
    baseline: dict[str, Any],
    proposed: dict[str, Any],
    *,
    track: str | None = None,
    reference_lap_time: float | None = None,
    conditions: str | None = None,
) -> SetupEstimate:
    """
    Estimate lap-time change proposed - baseline.
    Negative total_dt => proposed setup expected faster.
    """
    from .conditions import _as_state, is_wet_surface

    base = normalize_setup(baseline)
    prop = normalize_setup(proposed)
    pmap = _param_map()
    lines: list[SetupDeltaLine] = []
    breakdown = {
        "aero": 0.0,
        "transmission": 0.0,
        "geometry": 0.0,
        "suspension": 0.0,
        "brakes": 0.0,
        "tyres": 0.0,
        "fuel": 0.0,
    }

    state = _as_state(conditions)
    wet = is_wet_surface(state)
    t = (track or "").lower()
    high_downforce = any(x in t for x in ("monaco", "hungar", "singapore", "zandvoort"))
    power_track = any(x in t for x in ("monza", "baku", "jeddah", "las vegas", "spa"))
    aero_mult = 1.25 if high_downforce else (0.75 if power_track else 1.0)
    drag_mult = 1.35 if power_track else (0.8 if high_downforce else 1.0)
    if wet:
        # Extra DF pays more when the surface is slippery; drag cost shrinks relatively
        wet_boost = {"damp": 1.15, "inter": 1.35, "wet": 1.55}.get(state, 1.3)
        aero_mult *= wet_boost
        drag_mult *= 0.75

    for key, b in base.items():
        if key not in prop or key not in pmap:
            continue
        p = pmap[key]
        v = float(prop[key])
        du = v - b
        if abs(du) < 1e-9:
            continue

        if key == "wing_setup_0":
            est = du * (-0.014 * aero_mult + 0.006 * drag_mult)
            group = "aero"
        elif key == "wing_setup_1":
            est = du * (-0.010 * aero_mult + 0.011 * drag_mult)
            group = "aero"
        elif key.startswith("tyre_press"):
            disp_b = display_value(p, b)
            disp_v = display_value(p, v)
            if state == "wet":
                opt = 22.5 if key.endswith(("_0", "_1")) else 20.8
            elif state in ("inter", "damp"):
                opt = 23.5 if key.endswith(("_0", "_1")) else 21.2
            else:
                opt = 25.0 if key.endswith(("_0", "_1")) else 22.0
            pen_b = 0.004 * (disp_b - opt) ** 2
            pen_v = 0.004 * (disp_v - opt) ** 2
            est = pen_v - pen_b
            group = "tyres"
        elif key == "fuel_setup":
            est = du * FUEL_S_PER_KG
            group = "fuel"
        elif p.group == "Brakes":
            opt = 0.56
            if "press" in key:
                est = du * p.dt_per_unit
            else:
                est = (abs(v - opt) - abs(b - opt)) * 0.35 + du * 0.01
            group = "brakes"
        elif p.group == "Geometry":
            if key.startswith("camber"):
                opt = p.min_v  # meta = most negative allowed
                est = 0.006 * ((float(v) - opt) ** 2 - (float(b) - opt) ** 2)
            else:
                est = du * p.dt_per_unit * 0.15
            group = "geometry"
        else:
            est = du * p.dt_per_unit
            group = {
                "Aero": "aero",
                "Transmission": "transmission",
                "Suspension": "suspension",
                "Fuel": "fuel",
            }.get(p.group, p.group.lower())

        lines.append(
            SetupDeltaLine(
                key=key,
                label=p.label,
                baseline=b,
                proposed=v,
                delta_units=du,
                est_dt=float(est),
                note=p.notes,
            )
        )
        breakdown[group] = breakdown.get(group, 0.0) + float(est)

    total = float(sum(l.est_dt for l in lines))

    fw_du = prop.get("wing_setup_0", base.get("wing_setup_0", 0)) - base.get("wing_setup_0", prop.get("wing_setup_0", 0))
    rw_du = prop.get("wing_setup_1", base.get("wing_setup_1", 0)) - base.get("wing_setup_1", prop.get("wing_setup_1", 0))
    if abs(fw_du) < 0.1 and abs(rw_du) < 0.1:
        balance = "Aero balance unchanged."
    elif fw_du - rw_du > 1:
        balance = "More front-biased aero → expect more oversteer / sharper turn-in."
    elif rw_du - fw_du > 1:
        balance = "More rear-biased aero → expect more understeer / traction stability."
    else:
        balance = "Overall downforce level changed with similar balance."

    n = len(lines)
    if n == 0:
        conf = "No changes."
    elif n <= 3 and abs(total) < 0.25:
        conf = "Low–medium confidence (small tweak)."
    elif "fuel" in breakdown and abs(breakdown["fuel"]) > abs(total) * 0.6:
        conf = "Higher confidence on fuel mass; aero/mech are directional."
    else:
        conf = "Directional estimate — validate with a practice push after one change at a time."

    if reference_lap_time:
        total = float(np.clip(total, -0.08 * reference_lap_time, 0.08 * reference_lap_time))

    return SetupEstimate(
        baseline=base,
        proposed={**base, **prop},
        lines=sorted(lines, key=lambda x: abs(x.est_dt), reverse=True),
        total_dt=total,
        aero_balance_note=balance,
        confidence=conf,
        breakdown=breakdown,
    )


def setup_presets(baseline: dict[str, Any], conditions: str | None = None) -> dict[str, dict[str, float]]:
    """Handy one-click directions from the current garage."""
    from .conditions import _as_state, is_wet_surface

    b = normalize_setup(baseline)
    state = _as_state(conditions)
    wet = is_wet_surface(state)
    presets = {}
    if "wing_setup_0" in b and "wing_setup_1" in b:
        wing_step = 3 if wet else 2
        presets["More downforce"] = {
            **b,
            "wing_setup_0": min(50, b["wing_setup_0"] + wing_step),
            "wing_setup_1": min(50, b["wing_setup_1"] + wing_step),
        }
        if not wet:
            presets["Less drag"] = {
                **b,
                "wing_setup_0": max(0, b["wing_setup_0"] - 2),
                "wing_setup_1": max(0, b["wing_setup_1"] - 3),
            }
        else:
            presets["Wet DF push"] = {
                **b,
                "wing_setup_0": min(50, b["wing_setup_0"] + 4),
                "wing_setup_1": min(50, b["wing_setup_1"] + 5),
            }
    if "brake_bias_setup" in b:
        presets["Forward bias (stable)"] = {
            **b,
            "brake_bias_setup": min(0.62, b["brake_bias_setup"] + 0.02),
        }
        if not wet:
            presets["Rearward bias (careful)"] = {
                **b,
                "brake_bias_setup": max(0.55, b["brake_bias_setup"] - 0.01),
            }
    if "brake_press_setup" in b and b["brake_press_setup"] > 0.92:
        presets["Softer brake bite"] = {
            **b,
            "brake_press_setup": max(0.80, b["brake_press_setup"] - 0.05),
        }
    if "fuel_setup" in b:
        presets["Quali fuel (min)"] = {**b, "fuel_setup": 5.0}
        presets["Race fuel (+10)"] = {**b, "fuel_setup": min(110, b["fuel_setup"] + 10)}
    if "diff_onThrottle_setup" in b:
        presets["More exit rotation"] = {
            **b,
            "diff_onThrottle_setup": max(0.10, b["diff_onThrottle_setup"] - 0.10),
        }
    if wet and "arb_setup_1" in b:
        presets["Softer rear (traction)"] = {
            **b,
            "arb_setup_1": max(1, b["arb_setup_1"] - 2),
            "susp_spring_setup_1": max(1, b.get("susp_spring_setup_1", 10) - 2),
        }
    return presets


def estimate_to_frame(est: SetupEstimate) -> pd.DataFrame:
    if not est.lines:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "Parameter": ln.label,
                "Baseline": ln.baseline,
                "Proposed": ln.proposed,
                "Δ units": ln.delta_units,
                "Est. Δt (s)": ln.est_dt,
                "Note": ln.note,
            }
            for ln in est.lines
        ]
    )
