# 13: Real-game test of the engineer and the live duel (on the wheel)

**Status:** ready-for-human
**Area:** practice (priority) · verification

Neither the engineer test nor the live duel has run against the game yet (only replay + synthetic injection). The 2026-10-16 pad session (#51, Miami FP1, 3 laps 1:35.1-1:35.8) confirmed recording, forwarding to SRT/SimHub, TyreSets storage and ingest — not the engineer.

**Steps (Miami FP, Live page at http://127.0.0.1:8765/live):**
- [ ] server on a library copy: `.venv\Scripts\python.exe -m telemetria_server --app-root <copy>` (or the real library — the wheel/axes migration was checked on a copy, see summary)
- [ ] Race Engineer → **Short**: out-lap + 3 laps on variant 1, box, set variant 2 as instructed, 3 laps, box, answer 1 / 2 / same, confirm
- [ ] note anything the card said that did not make sense (instruction, detected variant, lap counting, result text)
- [ ] if time: Setup duel → 2 setups, 3 laps each
- [ ] leave to the menu so the session is saved; then check the Setups page (baseline offer) and the session's Corners tab

## Comments
