"""Generated setup for a track: collect evidence from the library, run the pure estimator, shape the API payload."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from telemetry import duel_store, engineer_log
from telemetry.garage import to_garage
from telemetry.garage_display import garage_display
from telemetry.setup_generator import Evidence, estimate_setup, fuel_samples, plan_fuel, prior_for
from telemetry.track_catalog import TRACK_LENGTHS_M
from telemetry.track_profile import similarity, track_profile

from . import track_baseline


class UnknownTrack(KeyError):
    pass


def collect_evidence(track: str, root: Path) -> list[Evidence]:
    """Baselines, engineer settled values and duel winners on every OTHER track, each with its similarity to ``track``."""
    raw: list[Evidence] = []
    with_profile: dict[str, Any] = {}

    def profile(t: str) -> dict[str, Any] | None:
        if t not in with_profile:
            try:
                with_profile[t] = track_profile(t, root)
            except (KeyError, ValueError, OSError):
                with_profile[t] = None
        return with_profile[t]

    for t, rows in _baseline_rows(root).items():
        raw.extend(Evidence(t, "baseline", to_garage(r["setup"]), 0.0, r["created_at"], r["name"]) for r in rows)
    for t, params in engineer_log.all_settled(root).items():
        for param, (value, when) in params.items():
            raw.append(Evidence(t, "settled", {param: value}, 0.0, when))
    for d in duel_store.list_duels(root):
        ranking = d["result"].get("ranking") or {}
        winner = ranking.get("winner")
        if not winner:
            continue
        try:
            setup, name = track_baseline._duel_setup(d["track"], d["id"], winner, root)
        except track_baseline.BaselineError:
            continue
        raw.append(Evidence(d["track"], "duel", setup, 0.0, d["started_at"], name or None))

    target = profile(track)
    out = []
    for e in raw:
        if e.track == track:
            if e.source != "baseline":  # its own baseline is the answer itself; its settled values / duel winner stay absolute
                e.similarity, e.own = 1.0, True
                out.append(e)
            continue
        if target is None:
            continue
        other = profile(e.track)
        if other is None:
            continue
        e.similarity = similarity(target, other)
        try:
            e.prior = prior_for(e.track)[0] if e.track in TRACK_LENGTHS_M and _has_prior(e.track) else None
        except KeyError:
            e.prior = None
        out.append(e)
    return out


def _has_prior(track: str) -> bool:
    """A track has its own typical setup (itself or its forward layout); the generic median does not count."""
    return prior_for(track)[1] != "table median"


def _baseline_rows(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Active baseline of every track that has one."""
    from telemetry.db import connect

    duel_store.ensure_duel_schema(root)
    with connect(root) as conn:
        tracks = [r["track"] for r in conn.execute("SELECT DISTINCT track FROM track_baselines")]
    out = {}
    for t in tracks:
        active = duel_store.get_baselines(t, root)["active"]
        if active:
            out[t] = [active]
    return out


def generated_setup(track: str, root: Path) -> dict[str, Any]:
    """The ``GET /tracks/{track}/generated-setup`` payload. Raises UnknownTrack off the catalogue."""
    if track not in TRACK_LENGTHS_M:
        raise UnknownTrack(track)
    profile = track_profile(track, root)
    evidence = collect_evidence(track, root)
    sim = {}
    for e in evidence:
        if not e.own:
            sim[e.track] = max(sim.get(e.track, 0.0), e.similarity)
    fuel = plan_fuel(track, fuel_samples(root), sim)
    prior, prior_source = prior_for(track)
    est = estimate_setup(evidence, prior, fuel_kg=fuel["race_kg"])
    setup = est["setup"]
    values = {k: v["value"] for k, v in setup.items()}
    display = [{**item, "confidence": setup[item["key"]]["confidence"], "source": setup[item["key"]]["source"]}
               for item in garage_display(values)]
    return {
        "track": track,
        "profile": profile,
        "setup": setup,
        "display": display,
        "overall_confidence": est["overall_confidence"],
        "group_confidence": est["group_confidence"],
        "first_test": est["first_test"],
        "fuel": fuel,
        "prior_source": prior_source,
        "evidence_tracks": sorted(sim, key=lambda t: -sim[t]),
    }
