# 10: Generated setup ignores the setups already driven at the track

**Status:** needs-triage
**Area:** pre-session / setups · engineering gap · severity medium

**What happens:** Miami has 4 sessions and 2 distinct driven setups (`0484b2a4` 6 runs, `a7e755d7` 3 runs), yet the generated setup is "typical-setup table only", every value **Low – prior only** (`screens/setups-miami.png`). Same at Spa after a recorded race. The generator's evidence is A/B results (engineer / duel), none exist yet, so everything falls back to the table — even though the driver has a setup that already works here.

Also on the page: 14 red "Low – prior only" pills, one per value, make the card look like an error list rather than a starting point.

**Decisions needed (triage):**
- use the best driven setup at the track (by corrected race pace, as the duel ranks) as a prior above the typical table, labelled "from your runs"
- confidence shown once per group (aero / mechanical / tyres) instead of on every value

## Comments
