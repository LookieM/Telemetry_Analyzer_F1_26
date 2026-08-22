"""Shared thresholds for coach / stint / insights producers."""

from __future__ import annotations

# Lockup sample count above which we flag braking issues (per lap).
LOCKUP_BRAKE_THRESHOLD = 15

# High-speed coast: neither throttle nor brake while still fast (pace technique).
COAST_HS_MIN_SPEED_KMH = 180

# Full-lap coast share (fuel-saving / stint management).
COAST_STINT_MIN_SPEED_KMH = 0
