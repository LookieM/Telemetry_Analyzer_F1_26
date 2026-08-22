"""
Track weather / surface state for setups and coaching.

Session `conditions` stays free-text in the DB; we encode a structured state
as a leading label (Dry / Damp / Intermediate / Wet) so legacy notes still work.
"""

from __future__ import annotations

from typing import Literal

TrackState = Literal["dry", "damp", "inter", "wet"]

TRACK_STATES: tuple[TrackState, ...] = ("dry", "damp", "inter", "wet")

STATE_LABELS: dict[TrackState, str] = {
    "dry": "Dry",
    "damp": "Damp",
    "inter": "Intermediate",
    "wet": "Wet",
}

STATE_OPTIONS = [STATE_LABELS[s] for s in TRACK_STATES]

_WET_TOKENS = ("wet", "full wet", "full-wet", "monsoon", "standing water", "rain", "raining")
_INTER_TOKENS = ("inter", "intermediate", "intermediates", "inters")
_DAMP_TOKENS = ("damp", "moist", "drizzle", "light rain", "spitting")
_DRY_TOKENS = ("dry", "slick", "slicks")


def label_to_state(label: str | None) -> TrackState:
    raw = (label or "").strip().lower()
    for state, lab in STATE_LABELS.items():
        if raw == lab.lower() or raw == state:
            return state
    return "dry"


def parse_track_state(text: str | None) -> TrackState:
    """Infer track state from free-text conditions (keyword scan)."""
    raw = (text or "").strip().lower()
    if not raw:
        return "dry"
    # Prefer more severe weather when multiple keywords appear
    if any(tok in raw for tok in _WET_TOKENS):
        # "light rain" / damp-only phrases should not force full wet
        if "light rain" in raw or raw.startswith("damp"):
            if not any(tok in raw for tok in ("wet", "full wet", "standing water", "monsoon")):
                return "damp"
        return "wet"
    if any(tok in raw for tok in _INTER_TOKENS):
        return "inter"
    if any(tok in raw for tok in _DAMP_TOKENS):
        return "damp"
    if any(tok in raw for tok in _DRY_TOKENS):
        return "dry"
    return "dry"


def _as_state(state: TrackState | str | None) -> TrackState:
    if state in TRACK_STATES:
        return state  # type: ignore[return-value]
    if isinstance(state, str) and state in STATE_LABELS.values():
        return label_to_state(state)
    return parse_track_state(state)


def is_wet_surface(state: TrackState | str | None) -> bool:
    return _as_state(state) in ("damp", "inter", "wet")


def is_full_wet(state: TrackState | str | None) -> bool:
    return _as_state(state) == "wet"


def compose_conditions(state: TrackState | str, notes: str = "") -> str:
    """Build the stored conditions string from structured state + optional notes."""
    st = _as_state(state)
    label = STATE_LABELS[st]
    notes = (notes or "").strip()
    for lab in STATE_LABELS.values():
        prefix = f"{lab} — "
        if notes.lower().startswith(prefix.lower()):
            notes = notes[len(prefix) :].strip()
        elif notes.lower() == lab.lower():
            notes = ""
    if st == "dry" and not notes:
        return ""
    if notes:
        return f"{label} — {notes}"
    return label


def split_conditions(text: str | None) -> tuple[TrackState, str]:
    """Return (state, notes without leading weather label)."""
    raw = (text or "").strip()
    state = parse_track_state(raw)
    notes = raw
    for lab in STATE_LABELS.values():
        for sep in (" — ", " - ", ": ", " | "):
            prefix = f"{lab}{sep}"
            if notes.lower().startswith(prefix.lower()):
                notes = notes[len(prefix) :].strip()
                return state, notes
        if notes.lower() == lab.lower():
            return state, ""
    return state, notes


def weather_banner(state: TrackState | str | None) -> str | None:
    s = state if state in TRACK_STATES else parse_track_state(state)
    if s == "dry":
        return None
    if s == "damp":
        return "Damp track — advice uses lower grip; dry warm-up / pressure tips are muted."
    if s == "inter":
        return "Intermediate conditions — setups and coaching target inter compounds, not slicks."
    return "Wet track — setups and coaching target full wets; dry slick baselines are not applied."
