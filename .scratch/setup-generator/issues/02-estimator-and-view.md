# 02: Generated setup with confidence on the Setups page

**What to build:** for a track without a baseline the Setups page shows a generated setup: per parameter a value blended from baselines / settled values / duel winners on similar tracks and the corrected typical-setup prior (race fuel from my consumption × 50 % laps, camber meta), snapped to garage steps/ranges with coherent suspension, with source, evidence and low/medium/high confidence, an overall confidence, a first-test suggestion and "Make baseline". See spec: Implementation Decisions "Evidence collection", "Estimator", "Fuel", "API", "React".

**Blocked by:** 01

**Status:** done

- [ ] Pure estimator + evidence collection; GET /api/tracks/{track}/generated-setup
- [ ] Make baseline with source "generator" (stores per-parameter confidence)
- [ ] Setups page view with badges, evidence rows, first test
- [ ] Tests: synthetic estimator cases, API on tmp library, vitest, headless Chrome
