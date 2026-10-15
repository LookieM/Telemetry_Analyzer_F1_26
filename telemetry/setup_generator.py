"""Setup generator: a starting garage setup for a track from what the app has learned elsewhere, with honest confidence.

Pure core (no DB): ``estimate_setup(evidence, prior)`` blends, per parameter, the setups found on *other* tracks
(similarity-weighted) with the typical-setup prior, snaps to the garage steps / ranges, keeps the suspension coherent
and camber at the meta, and grades every parameter low / medium / high from the evidence weight behind it.
``plan_fuel`` turns measured consumption into race / quali fuel. ``fuel_samples`` and ``prior_for`` read the library
and the typical-setup table. Evidence collection (baselines, settled values, duel winners) lives in
``telemetria_server.setup_generation``.

Transfer: a result found on another track is applied as its offset from that track's typical setup
(`prior_target + (found - prior_found)`, clamped to OFFSET_CLAMP_FRAC of the garage range); a result without a prior
counts as an absolute value only from tracks at least ABSOLUTE_MIN_SIMILARITY alike; the target's own results stay absolute.

Weights: an evidence item weighs ``similarity x SOURCE_WEIGHTS[source] x recency``; the prior is one
pseudo-observation of ``PRIOR_WEIGHT``. Confidence is read from the summed evidence weight (prior excluded):
below MEDIUM_WEIGHT -> "low" (prior only, or nearly), below HIGH_WEIGHT -> "medium", else "high".
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from . import db
from .corners import normalize_track_name
from .garage import to_garage
from .garage_display import _decimals
from .setup_builder import CAMBER_META
from .setup_tweaker import SETUP_PARAMS, SetupParam, display_value
from .track_catalog import RACE_SHARE, TRACK_LENGTHS_M, race_laps
from .track_profile import forward_name
from .track_setups import TRACK_TYPICAL_SETUPS, coherent_suspension, get_typical_setup

SOURCE_WEIGHTS: dict[str, float] = {"baseline": 1.0, "settled": 0.8, "duel": 1.0}
PRIOR_WEIGHT = 0.5
MIN_EVIDENCE_SIMILARITY = 0.10  # evidence from a track less alike than this is ignored
RECENCY_HALF_LIFE_DAYS = 120.0
RECENCY_FLOOR = 0.6  # old evidence never counts for less than this share
MEDIUM_WEIGHT = 0.5  # one reasonably similar result
HIGH_WEIGHT = 1.5  # about two close results, or several fair ones
LEVELS = ("low", "medium", "high")
OFFSET_CLAMP_FRAC = 0.5  # a transferred offset never exceeds this share of the parameter's garage range
ABSOLUTE_MIN_SIMILARITY = 0.8  # evidence from a track without a prior counts as an absolute value only this alike

AERO_KEYS = ("wing_setup_0", "wing_setup_1")
MECH_KEYS = (
    "diff_onThrottle_setup", "diff_offThrottle_setup", "arb_setup_0", "arb_setup_1",
    "susp_spring_setup_0", "susp_spring_setup_1", "susp_height_setup_0", "susp_height_setup_2",
    "brake_bias_setup", "brake_press_setup", "tyre_press_setup_0", "tyre_press_setup_2",
)
FIRST_TEST_PRIORITY = ("wing_setup_0", "wing_setup_1", "diff_onThrottle_setup", "arb_setup_0", "arb_setup_1")

# Left / right values are one garage entry: the right-hand key mirrors the left-hand one.
MIRRORS = {
    "susp_height_setup_1": "susp_height_setup_0", "susp_height_setup_3": "susp_height_setup_2",
    "tyre_press_setup_1": "tyre_press_setup_0", "tyre_press_setup_3": "tyre_press_setup_2",
}
ESTIMATED_KEYS = tuple(p.key for p in SETUP_PARAMS if p.key in {
    "wing_setup_0", "wing_setup_1", "diff_onThrottle_setup", "diff_offThrottle_setup", "toe_setup_0", "toe_setup_1",
    "susp_spring_setup_0", "susp_spring_setup_1", "arb_setup_0", "arb_setup_1",
    "susp_height_setup_0", "susp_height_setup_1", "susp_height_setup_2", "susp_height_setup_3",
    "brake_bias_setup", "brake_press_setup",
    "tyre_press_setup_0", "tyre_press_setup_1", "tyre_press_setup_2", "tyre_press_setup_3",
})

FUEL_MIN_KG = 5.0  # garage minimum, used for quali
FUEL_MAX_KG = 110.0
FUEL_MARGIN_LAPS = 1
FUEL_MIN_LAPS = 3  # measured laps needed on a track before its own median counts
FUEL_LAP_LIMITS = (0.1, 5.0)  # kg: below / above is a pit / refuel artefact
FUEL_SLOW_LAP_FACTOR = 1.08  # laps slower than this x the session's best lap (in / out / safety car) are skipped
FUEL_SIMILAR_MIN = 0.5  # a track this alike (or more) supplies kg/km for an unmeasured one
FUEL_DEFAULT_KG_PER_KM = 0.32  # last resort when the library has no consumption at all


@dataclass
class Evidence:
    """One setup (possibly partial, canonical garage units) found on another track."""

    track: str
    source: str  # baseline | settled | duel
    setup: Mapping[str, float]
    similarity: float
    date: str | None = None
    name: str | None = None
    prior: Mapping[str, float] | None = None  # that track's typical setup: results transfer as offsets from it
    own: bool = False  # the target track's own result: used as an absolute value


def recency_factor(date: str | None, now: datetime | None = None) -> float:
    if not date:
        return 1.0
    try:
        d = datetime.fromisoformat(str(date).replace("Z", "+00:00"))
    except ValueError:
        return 1.0
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    age = max(0.0, ((now or datetime.now(timezone.utc)) - d).total_seconds() / 86400.0)
    return max(RECENCY_FLOOR, 0.5 ** (age / RECENCY_HALF_LIFE_DAYS))


def confidence_level(weight: float) -> str:
    if weight >= HIGH_WEIGHT:
        return "high"
    if weight >= MEDIUM_WEIGHT:
        return "medium"
    return "low"


_PARAMS: dict[str, SetupParam] = {p.key: p for p in SETUP_PARAMS}


def snap(key: str, value: float) -> float:
    """Clip to the garage range and round to the garage step."""
    p = _PARAMS[key]
    v = min(max(float(value), p.min_v), p.max_v)
    snapped = p.min_v + round((v - p.min_v) / p.step) * p.step
    snapped = min(max(snapped, p.min_v), p.max_v)
    return snapped if p.unit == "psi" else round(snapped, 6)  # pressures are Pa: keep the exact step


def _evidence_value(setup: Mapping[str, float], key: str) -> float | None:
    """Value of ``key`` in one evidence setup; a left-hand key averages with its mirrored right-hand one."""
    vals = []
    for k in (key, *(m for m, base in MIRRORS.items() if base == key)):
        v = setup.get(k)
        if v is not None and math.isfinite(float(v)):
            vals.append(float(v))
    return sum(vals) / len(vals) if vals else None


def _transfer(key: str, e: Evidence, target_prior: float) -> tuple[float, float | None] | None:
    """(value for the target, offset or None) of one evidence item, or None when it cannot be used.
    Results transfer as the driver's offset from the typical setup of the track they came from."""
    v = _evidence_value(e.setup, key)
    if v is None:
        return None
    if e.own:
        return v, None
    pv = _evidence_value(e.prior, key) if e.prior else None
    if pv is None:
        return (v, None) if e.similarity >= ABSOLUTE_MIN_SIMILARITY else None
    p = _PARAMS[MIRRORS.get(key, key)]
    cap = OFFSET_CLAMP_FRAC * (p.max_v - p.min_v)
    offset = min(max(v - pv, -cap), cap)
    return target_prior + offset, offset


def _blend(key: str, evidence: list[Evidence], prior: float, now: datetime | None) -> dict[str, Any]:
    items = []
    num = PRIOR_WEIGHT * prior
    den = PRIOR_WEIGHT
    weight = 0.0
    seen: set[tuple[str, float]] = set()
    for e in sorted(evidence, key=lambda e: -SOURCE_WEIGHTS.get(e.source, 0.0)):
        if e.similarity < MIN_EVIDENCE_SIMILARITY:
            continue
        raw = _evidence_value(e.setup, key)
        if raw is None or (e.track, round(raw, 6)) in seen:  # the same setup reported as baseline and duel winner counts once
            continue
        got = _transfer(key, e, prior)
        if got is None:
            continue
        v, offset = got
        seen.add((e.track, round(raw, 6)))
        w = e.similarity * SOURCE_WEIGHTS.get(e.source, 0.0) * recency_factor(e.date, now)
        num += w * v
        den += w
        weight += w
        items.append({"track": e.track, "source": e.source, "value": v, "offset": offset, "found": raw, "similarity": e.similarity,
                      "weight": w, "name": e.name, "own": e.own})
    items.sort(key=lambda i: -i["weight"])
    return {"raw": num / den, "weight": weight, "evidence": items}


def _group_level(keys: tuple[str, ...], entries: Mapping[str, Mapping[str, Any]]) -> str:
    """A group's grade is the lower median of its parameters' grades (one odd parameter does not sink it)."""
    ranks = sorted(LEVELS.index(entries[k]["confidence"]) for k in keys if k in entries)
    return LEVELS[ranks[(len(ranks) - 1) // 2]] if ranks else "low"


def _first_test(entries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any] | None:
    cands = [k for k in FIRST_TEST_PRIORITY if k in entries]
    if not cands:
        return None
    key = min(cands, key=lambda k: (LEVELS.index(entries[k]["confidence"]), FIRST_TEST_PRIORITY.index(k)))
    e = entries[key]
    why = "prior only" if not e["evidence"] else e["confidence"]
    return {"key": key, "label": e["label"], "confidence": e["confidence"],
            "text": f"Test {e['label'].lower()} first (lowest confidence: {why})"}


def _entry(key: str, value: float, **extra: Any) -> dict[str, Any]:
    p = _PARAMS[key]
    shown = display_value(p, value)
    unit = (p.unit or "").strip()
    out = {"value": value, "display": round(shown, _decimals(unit, shown)), "unit": unit, "label": p.label}
    out.update(extra)
    return out


def estimate_setup(evidence: list[Evidence], prior: Mapping[str, float], *, fuel_kg: float | None = None,
                   now: datetime | None = None) -> dict[str, Any]:
    """The blend. ``prior`` is a canonical garage dict; returns
    ``{setup: {key: entry}, overall_confidence, group_confidence: {aero, mechanical}, first_test}`` with entries
    ``{value, display, unit, label, source (blend|prior|meta|consumption), confidence, weight, prior, evidence, note?}``."""
    prior = to_garage(prior)
    raw: dict[str, dict[str, Any]] = {}
    for key in ESTIMATED_KEYS:
        base = MIRRORS.get(key, key)
        if base in raw:
            raw[key] = raw[base]
            continue
        if key not in prior and base not in prior:
            continue
        raw[key] = _blend(key, evidence, float(prior.get(key, prior.get(base))), now)

    values = {k: snap(k, r["raw"]) for k, r in raw.items()}
    for key, base in MIRRORS.items():
        if key in values:
            values[key] = values[base]
    notes: dict[str, str] = {}
    if all(k in values for k in ("susp_spring_setup_0", "susp_spring_setup_1", "arb_setup_0", "arb_setup_1")):
        coh = coherent_suspension(values["susp_spring_setup_0"], values["susp_spring_setup_1"], values["arb_setup_0"], values["arb_setup_1"])
        for key, v in zip(("susp_spring_setup_0", "susp_spring_setup_1", "arb_setup_0", "arb_setup_1"), coh):
            v = snap(key, v)
            if v != values[key]:
                notes[key] = f"adjusted from {values[key]:g} to keep springs and anti-roll bars coherent"
                values[key] = v

    entries: dict[str, dict[str, Any]] = {}
    for key, r in raw.items():
        entries[key] = _entry(
            key, values[key], source="blend" if r["evidence"] else "prior", confidence=confidence_level(r["weight"]),
            weight=r["weight"], prior=snap(key, prior.get(key, prior.get(MIRRORS.get(key, key)))), evidence=r["evidence"],
            **({"note": notes[key]} if key in notes else {}))
    for key, target in CAMBER_META.items():
        entries[key] = _entry(key, snap(key, target), source="meta", confidence="high", weight=0.0, prior=target, evidence=[],
                              note="camber stays at the F1 26 meta")
    if fuel_kg is not None:
        entries["fuel_setup"] = _entry("fuel_setup", snap("fuel_setup", fuel_kg), source="consumption", confidence="high",
                                       weight=0.0, prior=None, evidence=[])

    groups = {"aero": _group_level(AERO_KEYS, entries), "mechanical": _group_level(MECH_KEYS, entries)}
    overall = min(groups.values(), key=LEVELS.index)
    order = {p.key: i for i, p in enumerate(SETUP_PARAMS)}
    return {
        "setup": dict(sorted(entries.items(), key=lambda kv: order.get(kv[0], 99))),
        "overall_confidence": overall,
        "group_confidence": groups,
        "first_test": _first_test(entries),
    }


# --------------------------------------------------------------------------- prior


def prior_for(track: str) -> tuple[dict[str, float], str]:
    """Typical-setup prior (race variant, canonical garage dict) and where it came from: the track's own table
    row, its forward layout's, or the per-parameter median of the whole table (Madring). Fuel is not part of it."""
    for name, label in ((track, "table"), (forward_name(track), "forward layout")):
        got = get_typical_setup(name, "race") if name else None
        if got:
            setup = {k: float(v) for k, v in to_garage(got["setup"]).items() if k != "fuel_setup"}
            return setup, label
    tables = [to_garage(v["race"]) for v in TRACK_TYPICAL_SETUPS.values()]
    keys = set.intersection(*(set(t) for t in tables))
    return {k: float(statistics.median(float(t[k]) for t in tables)) for k in keys if k != "fuel_setup"}, "table median"


# --------------------------------------------------------------------------- fuel


def fuel_samples(root: Path) -> dict[str, list[float]]:
    """Clean-lap fuel use per lap (kg) by catalogue track: laps within FUEL_SLOW_LAP_FACTOR of their session's best
    lap, with a plausible ``fuel_used`` (no pit / refuel artefacts)."""
    with db.connect(root) as conn:
        rows = conn.execute(
            "SELECT s.id AS sid, s.track AS track, l.lap_time AS t, l.fuel_used AS f "
            "FROM laps l JOIN sessions s ON s.id = l.session_id WHERE l.fuel_used IS NOT NULL AND l.lap_time > 0"
        ).fetchall()
    by_session: dict[int, list[Any]] = {}
    for r in rows:
        by_session.setdefault(int(r["sid"]), []).append(r)
    out: dict[str, list[float]] = {}
    for laps in by_session.values():
        track = normalize_track_name(laps[0]["track"]) or laps[0]["track"]
        if not track:
            continue
        best = min(float(r["t"]) for r in laps)
        for r in laps:
            f = float(r["f"])
            if float(r["t"]) <= best * FUEL_SLOW_LAP_FACTOR and FUEL_LAP_LIMITS[0] < f < FUEL_LAP_LIMITS[1]:
                out.setdefault(track, []).append(f)
    return out


def plan_fuel(track: str, samples: Mapping[str, list[float]], similarity: Mapping[str, float] | None = None) -> dict[str, Any]:
    """``{quali_kg, race_kg, kg_per_lap, race_laps, source}``. kg/lap = the track's own median measured use, else the
    similarity-weighted kg/km of alike measured tracks times this lap length, else the library-wide median kg/km
    times the length, else FUEL_DEFAULT_KG_PER_KM. Race fuel = kg/lap x (50 % race laps + margin lap), rounded up."""
    length_km = TRACK_LENGTHS_M.get(track, 5000.0) / 1000.0
    own = samples.get(track, [])
    per_km = {t: statistics.median(v) / (TRACK_LENGTHS_M[t] / 1000.0) for t, v in samples.items() if len(v) >= FUEL_MIN_LAPS and t in TRACK_LENGTHS_M and t != track}
    if len(own) >= FUEL_MIN_LAPS:
        kg_lap, source = float(statistics.median(own)), "measured on this track"
    else:
        alike = {t: s for t, s in (similarity or {}).items() if t in per_km and s >= FUEL_SIMILAR_MIN}
        if alike:
            kg_km = sum(per_km[t] * s for t, s in alike.items()) / sum(alike.values())
            kg_lap, source = kg_km * length_km, "similar tracks"
        elif per_km:
            kg_lap, source = float(statistics.median(per_km.values())) * length_km, "library kg/km"
        else:
            kg_lap, source = FUEL_DEFAULT_KG_PER_KM * length_km, "default kg/km"
    laps = race_laps(track) or race_laps(forward_name(track)) or math.ceil(55 * RACE_SHARE)
    race = float(min(FUEL_MAX_KG, max(FUEL_MIN_KG, math.ceil(kg_lap * (laps + FUEL_MARGIN_LAPS)))))
    return {"quali_kg": FUEL_MIN_KG, "race_kg": race, "kg_per_lap": round(kg_lap, 3), "race_laps": int(laps), "source": source}
