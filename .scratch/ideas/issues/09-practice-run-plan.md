# 09: Practice run plan with checklist and event log

**Status:** needs-triage
**Area:** practice · new feature · cost medium
**Source:** real F1 (run plan / run sheet for each session, event log of changes)

**Idea:** before FP the app proposes a programme for the 40–60 min, e.g. "1) baseline 3 laps, 2) engineer test of low-confidence parameters, 3) duel 2 setups × 3 laps, 4) long run 8 laps on C3 at race fuel". Live shows the current item and ticks it off from what is driven; an event log records setup / MFD changes and garage visits ("Return to garage" included). Afterwards: done vs planned.

**What exists:** engineer test (Short), setup duel, generator with confidence (it already picks what to test first), track baseline. They are separate tools; nothing plans the session or logs it as one.

**Decisions needed (triage):**
- generated plan vs editable template
- how items are detected as done (laps on a setup / compound, duel finished)
- new Live card or an extension of the Engineer card

**Depends on:** review/13 (wheel test of engineer + duel).

## Comments
