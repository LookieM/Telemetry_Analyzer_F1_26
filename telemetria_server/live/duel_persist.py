"""Store a finished live duel: the duel record and, when the driver confirmed a winner, the track baseline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from telemetry import duel_store
from telemetry.setup_history import compute_setup_fingerprint, mech_fingerprint

from .. import duel_library


def store_live_duel(result: dict[str, Any], app_root: Path | None) -> int:
    """Save the duel (mode "live") and make a confirmed winner the track's active baseline (source "duel")."""
    track = duel_library.track_name(result["track"])
    duel_id = duel_store.save_duel(track, "live", {**result, "track": track}, app_root)
    setup = result.get("winner_setup")
    if result.get("winner") and setup:
        name = (result.get("winner_name") or f"Duel {result.get('date') or ''}".strip())[:80]
        duel_store.set_baseline(
            track, setup, source="duel", name=name, ref_id=duel_id, app_root=app_root,
            fingerprint=mech_fingerprint(setup) or compute_setup_fingerprint(setup),
            meta={"winner_key": result["winner"], "mode": "live"})
    return duel_id
