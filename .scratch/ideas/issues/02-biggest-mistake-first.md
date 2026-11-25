# 02: "Biggest mistake first" — one ranked fix per lap

**Status:** needs-triage
**Area:** driver coaching · new feature / port · cost medium
**Source:** Track Titan "Coaching Flows" (walks the driver through the single biggest mistake on the lap and how to fix it); Coach Dave Delta "Auto Insights"

**Idea:** after a lap (or a run) name the ONE corner and phase where most time is lost, with the cause and a concrete instruction ("T4: brake 12 m later, you coast 0.4 s before turn-in — 0.21 s"), then the next one. Not a feed of 20 hints.

**What exists:** Corners tab gives per-corner time loss, brake/throttle points and "what changed" (`telemetry/corner_report.py` `callouts`). Streamlit-only `telemetry/coach.py` has a ranked coach feed with conflict resolution (`rank_coach_items`, `dedupe_and_resolve`) — not reachable from the React app (review/14).

**Decisions needed (triage):**
- reference: own best lap of the session, own lifetime best at the track, or ideal lap (01)
- port `coach.py` ranking or build fresh on top of `corner_report`
- show offline only (Session page) or also as a text line on Live in practice
- how many items (1, top 3?)

**Depends on:** review/08, review/09 (corner detection); relates to review/14.

## Comments
