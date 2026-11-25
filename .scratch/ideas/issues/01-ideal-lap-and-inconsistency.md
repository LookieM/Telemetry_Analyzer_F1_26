# 01: Ideal lap from best mini-sectors + inconsistency

**Status:** needs-triage
**Area:** session analysis (practice, qualifying) · new feature · cost low
**Source:** real F1 ("Ideal lap" / theoretical best: best time in every timing loop, summed); Race Technology "best theoretical lap"

**Idea:** sum the best mini-sector of the session (per compound / fuel class) into an ideal lap. Ideal minus best real lap = what the driver leaves through inconsistency; show which mini-sectors make up the gap and which lap each best piece came from.

**What exists:** `telemetry/metrics.py:614` `mini_sector_table` (20 mini-sectors, focus vs reference), shown in `LapsTab.tsx`. No session-wide best-per-sector, no ideal lap.

**Decisions needed (triage):**
- mini-sector split: equal distance (20) or corner-based from corner detection (depends on review/09)
- which laps count (push laps only — depends on review/08 partial-lap fix)
- also per-sector consistency (spread of a sector over push laps) as a coaching signal?
- place: Laps tab header, Session overview, or both

**Depends on:** review/08 (partial laps counted as push).

## Comments
