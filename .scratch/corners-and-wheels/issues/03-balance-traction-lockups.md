# 03: Balance per corner and phase from slip angles, traction and per-wheel lock-ups

**What to build:** the Corners tab shows the car's balance per corner and phase (entry / mid / exit) measured as front minus rear slip angle (positive = understeer), traction on exit from rear slip on throttle, and lock-ups per wheel with where they happened — for the selected lap and as the median over the session's clean laps — plus a one-line balance summary. Sessions without slip channels say so. See spec: Solution 3, Implementation Decisions "Balance", "API".

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Pure balance function per corner/phase (understeer index in degrees, traction, lock-ups per wheel with distance and corner)
- [ ] Session view: median over clean laps; available=false with a reason when channels are missing
- [ ] /corners rows carry balance; GET /api/sessions/{id}/balance returns per-corner/phase medians + summary
- [ ] Corners tab: phase × corner balance heat strip, summary line, lock-up list
- [ ] Synthetic sign tests; Austria Q1 vs Q2 (diff on-throttle 55 → 80 %) exit-phase check — if the metric does not move, it is hidden and the finding is written into this ticket
- [ ] vitest for colour/summary helpers; headless Chrome check
