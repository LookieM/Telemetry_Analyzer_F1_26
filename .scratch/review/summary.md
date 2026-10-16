# Project review — 2026-10-16

Agreed in a grilling session: judge the project **as a race engineer's tool**, weighted to **practice (engineer, duel, long run)** and **the live race (BOX/STAY, SC, tyres, fuel, ERS, rivals, damage)**; architecture as "design"; UI only where it hurts a decision; report only, no fixes.

## What was run

| Check | Result |
|---|---|
| pytest | 393 passed, 3 skipped |
| vitest + tsc | 122 passed, typecheck clean |
| Library copy + startup migrations (`setup_reread_v1`, `wheel_axes_fix_v1`) | ran on all 43 sessions, 664 MB backup; g_long ≈ −3 g under braking, +1.2 g on throttle in both compact and full imports → **safe to run on the real library** (the real library has not run either migration yet; both run on its next server start) |
| Every page in headless Chrome (15 pages, sessions #16 #45 #47 #49, Live idle) | no console errors, no HTTP errors |
| UDP replay through Live (Spa race, 1100 s capture at ×3) at 1080×1920 | recorded and ingested as #50; findings 01-05 |
| Real game, pad, Miami FP1 (#51, 3 laps) | recording, SRT/SimHub forward, TyreSets, ingest OK; engineer / duel **not** exercised → 13 |

Screenshots: `screens/`.

## Findings, by priority

| # | Finding | Area | Status |
|---|---|---|---|
| 01 | Formation lap triggers "BOX under SC" | race live | ready-for-agent |
| 08 | Incomplete laps counted as push (Miami race "best" lap is partial; Baku Δ −13.5 s) | all analysis | ready-for-agent |
| 03 | Pit loss measured from incident laps (Spa 85.9 s) — poisons planner + live call | race | ready-for-agent |
| 07 | Offline duel uses 0.03 s/kg fuel effect, live uses measured 0.10 s/kg | practice / setups | ready-for-agent |
| 04 | Live layout ignores session type — rivals cut to 1 row in a race | race live UI | ready-for-agent |
| 02 | Live strategy ignores the stint's real wear / pace | race live | needs-triage |
| 06 | Engineer A→B order: session drift not cancelled; minimum detectable difference not shown | practice | needs-triage |
| 09 | Corner detection: no flat corners, merged complexes, names off by one | corners → profile → generator | needs-triage |
| 05 | No rejoin / traffic prediction; SC = VSC pit factor | race live | needs-triage |
| 10 | Generated setup ignores setups already driven at the track | setups | needs-triage |
| 13 | Real-game test of engineer + live duel on the wheel | practice | ready-for-human |
| 11 | Raw track names in Library / session header (Track42, Austria, Catalunya) | library | ready-for-agent |
| 12 | Small UI / data issues (7 items) | various | ready-for-agent |
| 14 | Streamlit retirement: 10 dead modules + parity gap list; no wet strategy | architecture | needs-triage |
| 15 | Architecture seams (engine → API import, 890-line engine, hand-written TS types) | architecture | needs-triage |
| 16 | Visual polish, dark only (user request) | UI | needs-triage |

## What works well

- Live view survives a full race replay with damage, pit stop and SC without errors; the front-wing call ("box for a new wing now — cheaper under the safety car") and fuel margin are what an engineer would say.
- Planner: clear ranked plans, sensitivity table, stint bars; sources ("measured / assumed") are shown.
- Corners tab: per-corner time loss, brake / throttle points and "what changed" is the right debrief shape (once 08 and 09 fix its inputs).
- Recording matches SRT channel by channel; relaying to SRT and SimHub works with the real game.
