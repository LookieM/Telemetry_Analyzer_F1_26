"""
Garage setup reader: SRT-convention setup channels -> the setup as the in-game garage shows it.

Raw channels (SRT exports, and our UDP recorder which writes the same convention):
per-wheel arrays ``_0.._3`` are front-first (0=FL, 1=FR, 2=RL, 3=RR), camber/toe in radians,
tyre pressures in Pa, diff / brake pressure / bias / engine braking as 0-1 fractions.

Canonical garage setup (keys of ``setup_tweaker.SETUP_PARAMS``): paired parameters (wing, camber, toe,
spring, ARB) use ``_0`` = front and ``_1`` = rear, in degrees for camber/toe. Ride heights and tyre
pressures stay per wheel (FL, FR, RL, RR). Values are never clipped: an out-of-range reading is a
reading error to surface (``out_of_range``), not to hide.

Raw vs canonical (so converting twice is a no-op), see ``is_raw_setup``: a dict is raw when it has the
rear-axle wheel slots (``camber/toe/susp_spring_setup_2|3``), which canonical dicts never carry, or when
``camber_setup_0`` is below 0.2 in magnitude (radians; canonical camber is at least 1 degree).
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

# Raw per-wheel params that collapse to canonical front (_0) / rear (_1); front = FL (0), rear = RL (2).
AXLE_PARAMS: tuple[str, ...] = ("camber_setup", "toe_setup", "susp_spring_setup")
# Raw params that stay per wheel and are only checked for left/right symmetry.
_SYMMETRY_PARAMS: tuple[str, ...] = AXLE_PARAMS + ("susp_height_setup",)
_ANGLE_PARAMS = ("camber_setup", "toe_setup")
# Channels passed through unchanged (already in the canonical unit and wheel layout).
_PASSTHROUGH: tuple[str, ...] = (
    "fuel_setup",
    "wing_setup_0",
    "wing_setup_1",
    "diff_onThrottle_setup",
    "diff_offThrottle_setup",
    "arb_setup_0",
    "arb_setup_1",
    "susp_height_setup_0",
    "susp_height_setup_1",
    "susp_height_setup_2",
    "susp_height_setup_3",
    "brake_bias_setup",
    "brake_press_setup",
    "brake_engine_setup",
    "front_brake_bias",
    "ballast_setup",
    "tyre_press_setup_0",
    "tyre_press_setup_1",
    "tyre_press_setup_2",
    "tyre_press_setup_3",
    "tyre_compound",
)
_RAD_LIMIT = 0.2  # |camber| below this (rad ~ 11 deg) cannot be a garage value in degrees


def _num(raw: Mapping[str, Any], key: str) -> float | None:
    v = raw.get(key)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f


def is_raw_setup(setup: Mapping[str, Any] | None) -> bool:
    """True for SRT-convention channels (radians, per-wheel arrays), False for an already canonical garage dict."""
    if not setup:
        return False
    if any(f"{p}_{i}" in setup for p in AXLE_PARAMS for i in (2, 3)):
        return True
    cam = _num(setup, "camber_setup_0")
    return cam is not None and abs(cam) < _RAD_LIMIT


def garage_from_raw(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Raw SRT-convention channels -> canonical garage setup. Pure, never clips.

    Camber and toe become degrees snapped to the garage resolution (0.01 deg) so one setup
    fingerprints to one value. A rear value is only produced when its wheel slot (index 2) exists.
    """
    if not raw:
        return {}
    out: dict[str, Any] = {k: raw[k] for k in _PASSTHROUGH if _num(raw, k) is not None}
    for p in AXLE_PARAMS:
        for axle, idx in ((0, 0), (1, 2)):
            v = _num(raw, f"{p}_{idx}")
            if v is None:
                continue
            out[f"{p}_{axle}"] = round(float(np.degrees(v)), 2) if p in _ANGLE_PARAMS else v
    return {k: float(v) for k, v in out.items()}


def to_garage(setup: Mapping[str, Any] | None) -> dict[str, Any]:
    """Canonical garage setup from either a raw channel dict or an already canonical one (idempotent)."""
    if not setup:
        return {}
    return garage_from_raw(setup) if is_raw_setup(setup) else dict(setup)


def raw_asymmetry(raw: Mapping[str, Any] | None) -> dict[str, tuple[float, float]]:
    """Axle params whose left and right wheel differ in a raw dict, as ``{canonical_key: (left, right)}``.

    The reader keeps front = FL / rear = RL; this exposes a mismatch instead of averaging it away.
    Values are in garage units (degrees for camber/toe).
    """
    out: dict[str, tuple[float, float]] = {}
    if not raw:
        return out
    for p in _SYMMETRY_PARAMS:
        for axle, (li, ri) in enumerate(((0, 1), (2, 3))):
            left, right = _num(raw, f"{p}_{li}"), _num(raw, f"{p}_{ri}")
            if left is None or right is None:
                continue
            if p in _ANGLE_PARAMS:
                left, right = round(float(np.degrees(left)), 2), round(float(np.degrees(right)), 2)
            if abs(left - right) > 1e-6:
                out[f"{p}_{li}" if p == "susp_height_setup" else f"{p}_{axle}"] = (left, right)
    return out


def out_of_range(setup: Mapping[str, Any] | None, *, tol: float = 1e-6) -> dict[str, tuple[float, float, float]]:
    """Canonical values outside their garage range, as ``{key: (value, min, max)}``."""
    from .setup_tweaker import SETUP_PARAMS

    out: dict[str, tuple[float, float, float]] = {}
    for p in SETUP_PARAMS:
        v = _num(setup or {}, p.key)
        if v is not None and (v < p.min_v - tol or v > p.max_v + tol):
            out[p.key] = (v, p.min_v, p.max_v)
    return out
