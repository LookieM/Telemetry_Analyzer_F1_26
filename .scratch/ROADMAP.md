# Setup-engineer roadmap

Agreed 2026-10-14 (grilling session). Each step: spec → tickets → implement. Local git only, never push.

1. **Setup reading fix** — done (`2a33995`). Spec: `live-engineer/spec.md`.
2. **Live engineer (optometrist test in practice)** — done (backend `2247f35`, Engineer card `c06a625`). Spec: `live-engineer/spec.md`.
3. **Wheel order + g-forces + lap/corner views** — done 2026-10-15 (`c1a373e` … `24fe8c6`). Spec + tickets: `corners-and-wheels/`.
4. **Setup duel** — done 2026-10-15 (`a24b7aa`, `24fe8c6`, `9f2f9b1`, `d56ee1e`): offline on the Setups page, live in the Engineer card, track baseline. Spec + tickets: `setup-duel/`.
5. **Computing a setup from scratch** — done 2026-10-15 (`83479e4`, `d56ee1e`, `289767b`): track profile, generator with confidence, engineer tests low-confidence parameters first. Spec + tickets: `setup-generator/`.

Next: real-game check in practice (engineer corner A/B, live duel), then phase 5.3+ (Energy, Setup/stints, Debrief, Track page, retire Streamlit).

**Review 2026-10-16** (grilling → report only): `.scratch/review/summary.md`, tickets `review/issues/01-16`. Top: 01 formation-lap BOX, 08 partial laps as push, 03 pit loss from incident laps, 07 fuel constant mismatch, 04 Live layout per session. Next: 16 visual polish (dark only), wheel test of the engineer (13).
