"""Corner profile of a live lap for the engineer: finds the track's corners and applies ``corner_profile``.

Corners come from the library's stored per-track corners; a track without any is built from the first full live
lap seen and kept in memory for the session (not stored: a library lap defines them later).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from telemetry import corner_store
from telemetry.corner_detect import detect_corners
from telemetry.corner_profile import MIN_COVERAGE, corner_profile, frame_coverage
from telemetry.corners import normalize_track_name
from telemetry.track_catalog import TRACK_CORNERS_FRAC, TRACK_LENGTHS_M

log = logging.getLogger("telemetria.live")


class LapProfiler:
    def __init__(self, root: Path | None) -> None:
        self.root = root
        self._corners: dict[str, list[dict[str, Any]]] = {}

    def corners_for(self, track: str, frame: pd.DataFrame, track_length: float) -> list[dict[str, Any]]:
        if track in self._corners:
            return self._corners[track]
        stored = None
        if self.root is not None:
            try:
                stored = corner_store.get_track_corners(track, self.root)
            except Exception:
                log.exception("could not read the stored corners of %s", track)
        corners = stored["corners"] if stored else detect_corners(
            frame, TRACK_CORNERS_FRAC.get(track), TRACK_LENGTHS_M.get(track) or track_length)
        self._corners[track] = corners
        return corners

    def profile(self, track_name: str | None, frame: pd.DataFrame, track_length: float) -> dict | None:
        """None for a lap frame that covers < 95 % of the lap distance or when no corners are known."""
        track = normalize_track_name(track_name)
        if not track or frame_coverage(frame, track_length) < MIN_COVERAGE:
            return None
        corners = self.corners_for(track, frame, track_length)
        return corner_profile(frame, corners) or None
