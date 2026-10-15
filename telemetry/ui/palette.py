"""Trace colours that stay readable on both the light and the dark Streamlit theme."""

FOCUS = "#E03C31"
REF = "#3E7CC9"
THROTTLE = "#2E9E44"
BRAKE = "#D7263D"
GEAR = "#8A6FD1"
NEUTRAL = "#8A9099"
DELTA = "#E8A317"

# Per-wheel colours, keyed by SRT wheel index (0=RL, 1=RR, 2=FL, 3=FR).
WHEEL = {0: "#3E7CC9", 1: "#E8A317", 2: "#2E9E44", 3: "#D7263D"}  # export order FL, FR, RL, RR
