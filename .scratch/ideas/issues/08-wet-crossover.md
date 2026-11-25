# 08: Wet strategy and slick ↔ inter crossover call

**Status:** needs-triage
**Area:** race live + Planner · new feature · cost medium
**Source:** real F1 (crossover lap time where inters become faster than slicks, and back); SimRacingSetup weather forecast overlay

**Idea:** from the forecast (already in the UDP Session packet) and live lap times on the current tyre vs a crossover estimate, call "BOX for inters in 2 laps (rain 80 % in 5 min)" and the reverse. Planner: plans with a weather change.

**What exists:** forecast read live (`telemetria_server/live/engine.py`, `Live.tsx`); the engine stops at weather ≥ 3 ("Wet running: no live dry-strategy call"); `telemetry/conditions.py` only labels track states. Gap listed in review/14.

**Decisions needed (triage):**
- crossover source: fixed seed delta per state vs measured from the library (few wet sessions?)
- how far the game forecast is trusted
- scope: live call only, or the Planner too

## Comments
