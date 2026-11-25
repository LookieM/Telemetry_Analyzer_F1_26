# 03: Racing line comparison against a reference lap

**Status:** needs-triage
**Area:** driver coaching · new feature · cost medium
**Source:** Coach Dave Delta, GO Fast, SimRacingSetup Pro (line comparison vs own best / pro lap)

**Idea:** draw two laps' lines on the track map (zoomed per corner): where the reference turns in, apexes and tracks out vs this lap; colour the line by speed delta. Plus a stored **reference lap per track** (lifetime best on comparable fuel / compound) so any session can be compared to it.

**What exists:** world positions in the data (`telemetry/loader.py:23-25` pos_x/pos_y/pos_z); `TrackMap` component with corner zoom (Corners tab, Laps tab); "Another session" reference in the Laps tab. No line overlay of two laps, no persistent per-track reference lap. Note: live delta vs PB was removed from Live at the driver's request — this ticket is offline unless decided otherwise.

**Decisions needed (triage):**
- precision: is the world position precise enough at 1 m bins to show a line difference of ~0.5 m? (check on a real lap pair first)
- reference choice: lifetime best per track vs best with the same setup / compound
- lateral offset as a chart (metres from the reference line vs distance) in addition to the map?

## Comments
