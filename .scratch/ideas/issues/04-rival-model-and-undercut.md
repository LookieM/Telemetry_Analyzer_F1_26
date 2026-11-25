# 04: Rival model — pace, degradation, predicted stop, undercut / overcut calculator

**Status:** needs-triage
**Area:** race live · new feature · cost medium-high
**Source:** real F1 strategy groups (each rival's pace and deg tracked live, undercut / overcut windows)

**Idea:** for cars within ±5 positions keep a per-stint model from their lap history: pace, deg per lap, tyre age → predicted stop lap. On top: "box now → rejoin P7, 1.2 s behind X (C3, 8 laps older)" and an undercut / overcut verdict against the car ahead / behind.

**What exists:** `telemetria_server/live/engine.py:790` `_rivals` = snapshot only (gap, compound, age, stops, last lap) and a crude `threat` flag (`engine.py:830`). The live state already keeps **SessionHistory per car** (`telemetria_server/live/state.py:17`) — every rival's lap times and tyre stints are available. Rejoin position is already proposed in review/05.

**Decisions needed (triage):**
- merge with review/05 (rejoin + SC/VSC factor) or keep 05 as the first slice of this one
- AI rivals: is their deg worth modelling or do AI cars follow a fixed pace profile? (measure on a recorded race)
- may the rival model change the BOX/STAY call or only inform it

**Depends on:** review/03 (pit loss), review/05.

## Comments
