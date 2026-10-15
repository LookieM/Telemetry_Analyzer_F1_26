"""A canonical garage setup as the ordered value list to type into the game (game order, game units). Pure."""

from __future__ import annotations

from typing import Any, Mapping

from .garage import to_garage
from .setup_tweaker import SETUP_PARAMS, display_value

GROUP_ORDER = ("Fuel", "Aero", "Transmission", "Geometry", "Suspension", "Brakes", "Tyres")
_HIDDEN = {"front_brake_bias"}  # live mirror of brake_bias_setup


def _decimals(unit: str, shown: float) -> int:
    if unit in ("psi", "°"):
        return 2
    if unit.startswith("%") or unit == "kg" or abs(shown - round(shown)) < 1e-6:
        return 0
    return 2


def garage_display(setup: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """``[{group, key, label, value, unit}]`` for every known garage value present, in garage order.

    ``value`` is in the game's units (psi, %, degrees, clicks) rounded to what the garage shows.
    """
    garage = to_garage(setup)
    order = {g: i for i, g in enumerate(GROUP_ORDER)}
    params = sorted((p for p in SETUP_PARAMS if p.key in garage and p.key not in _HIDDEN), key=lambda p: order.get(p.group, 99))
    out = []
    for p in params:
        shown = display_value(p, float(garage[p.key]))
        unit = (p.unit or "").strip()
        out.append({"group": p.group, "key": p.key, "label": p.label, "value": round(shown, _decimals(unit, shown)), "unit": unit})
    return out


def display_text(items: list[dict[str, Any]]) -> str:
    """Plain text of ``garage_display`` output, one ``Label: value unit`` per line under group headings."""
    lines: list[str] = []
    group = None
    for it in items:
        if it["group"] != group:
            group = it["group"]
            lines.append(f"{group}")
        unit = it["unit"]
        suffix = "%" if unit.startswith("%") else unit if unit == "°" else (f" {unit}" if unit else "")
        lines.append(f"  {it['label']}: {it['value']:g}{suffix}")
    return "\n".join(lines)
