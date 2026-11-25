# 10: Automatic race debrief

**Status:** needs-triage
**Area:** race analysis · new page (phase 5.3 "Debrief") · cost medium
**Source:** real F1 (post-race report: plan vs actual, stop costs, positions lost / gained, stint degradation)

**Idea:** one page after a race: planned vs actual strategy and what it cost, time per stop (in-lap + stop + out-lap), positions gained / lost per lap and why (stop, SC, overtake, incident), stint degradation vs model, damage cost, and 3 lessons for the next race at the track.

**What exists:** `telemetry/strategy.py` `RaceReview` (strategy cost vs best plan, execution vs model, missing / SC laps, over-limit stints) and `game_pit_windows`; Strategy tab. Positions per lap are in the export. No single debrief page.

**Decisions needed (triage):**
- content order and what goes into "lessons" (feed the Planner overrides?)
- include rivals (needs 04) or own car only first

**Depends on:** review/03, review/08.

## Comments
