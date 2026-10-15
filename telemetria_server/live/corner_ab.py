"""Corner / phase comparison of two engineer variants from per-lap corner profiles. Pure and I/O-free.

A profile is ``{corner_id: {name, speed_class, time_s, phases: {entry, mid, exit}, understeer: {entry, mid, exit},
traction}}`` (see ``telemetry.corner_profile``); this module only averages and compares them.
Times are scaled per lap by ``corrected lap time / raw lap time`` so the fuel and tyre-age correction is spread
over the lap by each corner's share of the lap time.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

MIN_PROFILE_LAPS = 2
TOP_ROWS = 5
SAME_S = 0.005  # a time difference below this says nothing for or against a tag
PHASES = ("entry", "mid", "exit")


def _mean(values: Sequence[float | None]) -> float | None:
    v = [x for x in values if x is not None and np.isfinite(x)]
    return float(np.mean(v)) if v else None


def average_profile(items: Sequence[tuple[dict, float]]) -> dict[Any, dict[str, Any]]:
    """Mean profile over laps; ``items`` are (profile, time scale) pairs. A corner is averaged over the laps that have it."""
    ids: dict[Any, None] = {}
    for prof, _ in items:
        ids.update(dict.fromkeys(prof))
    out: dict[Any, dict[str, Any]] = {}
    for cid in ids:
        rows = [(p[cid], k) for p, k in items if cid in p]
        first = rows[0][0]
        out[cid] = {
            "name": first["name"], "speed_class": first["speed_class"],
            "time_s": float(np.mean([r["time_s"] * k for r, k in rows])),
            "phases": {ph: float(np.mean([r["phases"][ph] * k for r, k in rows])) for ph in PHASES},
            "understeer": {ph: _mean([r["understeer"][ph] for r, _ in rows]) for ph in PHASES},
            "traction": _mean([r["traction"] for r, _ in rows]),
        }
    return out


def _diff(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else float(b - a)


def corner_table(p1: dict[Any, dict], p2: dict[Any, dict]) -> list[dict[str, Any]]:
    """Every corner x phase present in both variants: variant 2 minus variant 1."""
    rows = []
    for cid in p1:
        if cid not in p2:
            continue
        a, b = p1[cid], p2[cid]
        for ph in PHASES:
            rows.append({
                "corner": cid, "name": a["name"], "speed_class": a["speed_class"], "phase": ph,
                "delta_s": float(b["phases"][ph] - a["phases"][ph]),
                "understeer_delta_deg": _diff(a["understeer"][ph], b["understeer"][ph]),
                "traction_delta": _diff(a["traction"], b["traction"]) if ph == "exit" else None,
            })
    return rows


def top_rows(table: list[dict[str, Any]], n: int = TOP_ROWS) -> list[dict[str, Any]]:
    """The ``n`` largest |delta_s| rows, without the speed class."""
    rows = sorted(table, key=lambda r: -abs(r["delta_s"]))[:n]
    return [{k: v for k, v in r.items() if k != "speed_class"} for r in rows]


def _classes(tag: str) -> tuple[str, ...] | None:
    return ("slow",) if tag.endswith("_slow") else ("medium", "fast") if tag.endswith("_fast") else None


def _group(tag: str) -> tuple[str, tuple[str, ...] | None] | None:
    """(phase, speed classes or None for all corners) a tag talks about; None for tags the stopwatch cannot judge."""
    if tag == "traction":
        return "exit", None
    if tag.startswith("braking_"):
        return "entry", None
    for ph in PHASES:
        if tag.startswith(ph + "_") and _classes(tag):
            return ph, _classes(tag)
    return None


def tag_check(table: list[dict[str, Any]], tags: Sequence[str], verdict: str, labels: dict[str, str]) -> list[dict[str, Any]]:
    """Per mappable tag: the summed phase time difference over the matching corners (variant 2 minus 1), whether its
    sign agrees with the driver's verdict ("1" / "2"; None for "same" or a difference below ``SAME_S``) and a sentence.
    "traction" agrees on the exit rear-slip difference (less wheelspin = better) when it was measured."""
    out = []
    for tag in tags:
        grp = _group(tag)
        if grp is None:
            continue
        ph, classes = grp
        rows = [r for r in table if r["phase"] == ph and (classes is None or r["speed_class"] in classes)]
        if not rows:
            continue
        delta = float(sum(r["delta_s"] for r in rows))
        basis, floor = delta, SAME_S
        if tag == "traction":
            tr = [r["traction_delta"] for r in rows if r["traction_delta"] is not None]
            if tr and abs(float(np.mean(tr))) > 1e-3:
                basis, floor = float(np.mean(tr)), 1e-3
        agrees: bool | None = None
        if verdict in ("1", "2") and abs(basis) >= floor:
            agrees = (basis < 0) == (verdict == "2")
        label = labels.get(tag, tag)
        if abs(delta) < SAME_S:
            fact = "no measurable time difference there"
        else:
            fact = f"Variant {'2' if delta < 0 else '1'} is {abs(delta):.2f} s faster there"
        end = "" if agrees is None else (" — agrees with you" if agrees else " — disagrees with you")
        out.append({"tag": tag, "delta_s": round(delta, 4), "agrees": agrees, "text": f"{label}: {fact}{end}"})
    return out
