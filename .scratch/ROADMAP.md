# Setup-engineer roadmap

Agreed 2026-10-14 (grilling session). Each step: spec → tickets → implement. Local git only, never push.

1. **Setup reading fix** — done (`2a33995`). Spec: `live-engineer/spec.md`.
2. **Live engineer (optometrist test in practice)** — done (backend `2247f35`, Engineer card `c06a625`). Spec: `live-engineer/spec.md`.
3. **Wheel order + g-forces + lap/corner views** — done 2026-10-15 (`c1a373e` … `24fe8c6`). Spec + tickets: `corners-and-wheels/`.
4. **Setup duel** — done 2026-10-15 (`a24b7aa`, `24fe8c6`, `9f2f9b1`, `d56ee1e`): offline on the Setups page, live in the Engineer card, track baseline. Spec + tickets: `setup-duel/`.
5. **Computing a setup from scratch** — done 2026-10-15 (`83479e4`, `d56ee1e`, `289767b`): track profile, generator with confidence, engineer tests low-confidence parameters first. Spec + tickets: `setup-generator/`.

Next: real-game check in practice (engineer corner A/B, live duel), then phase 5.3+ (Energy, Setup/stints, Debrief, Track page, retire Streamlit).

**Review 2026-10-16** (grilling → report only): `.scratch/review/summary.md`, tickets `review/issues/01-16`. Top: 01 formation-lap BOX, 08 partial laps as push, 03 pit loss from incident laps, 07 fuel constant mismatch, 04 Live layout per session. Next: 16 visual polish (dark only), wheel test of the engineer (13).

**Visual polish 2026-10-16** — done (`169166b`, `f2f78db`, `6ed014a`, `eed7a58`; tickets 04 + 16 closed): dark-only pit-wall + F1 look on every page, Live cards follow the session type.

## Plan for the next session (agreed 2026-10-16)

1. **Wheel test in the game** (ticket 13): start the app as usual with `run_server.bat` on the real library — the first start runs the two one-off migrations (`setup_reread_v1`, `wheel_axes_fix_v1`; verified on a copy, they back up first, ~660 MB in `data/backups`). Miami FP → Live → Race Engineer **Short**; garage visits via the menu's "Return to garage" (that is how the driver works). Then, if time, Setup duel with 2 setups × 3 laps. Afterwards: check the stored test / duel, the Setups page and the session's Corners tab; write findings into ticket 13.
2. **Fix the ready tickets**, in this order, each: ticket → Sonnet subagent (medium) → Opus review + tests + local commit:
   - 01 formation lap triggers "BOX under SC"
   - 08 partial laps and garage out-laps counted as push (recorder keeps `driverStatus`, garage = end of lap, re-classify stored sessions)
   - 03 pit loss measured from incident laps (Spa 85.9 s)
   - 07 one fuel-effect constant (offline duel 0.03 vs measured 0.10 s/kg)
   - 11 raw track names in Library / session header; 12 small UI / data items
3. **Triage the open design tickets** with the driver (grilling): 02 live wear in the strategy, 06 engineer A/B order + detectable difference, 09 corner detection (flat corners, complexes, names), 05 rejoin position / VSC factor, 10 generator uses driven setups.
4. Later: 14 retire Streamlit (port or drop the gap list), 15 architecture seams, then phase 5.3+ (Energy, Setup/stints, Debrief, Track page).
