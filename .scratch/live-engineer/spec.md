Status: ready-for-agent

# Live race engineer: correct setup reading + optometrist-style setup test

## Problem Statement

I race F1 26 offline (Moza R5 + SRP Lite pedals, no assists, 50% race distance) and use this app because I
enjoy looking at telemetry; setups are the pretext. Today the app's setup advice cannot be trusted: it only
lives in the old Streamlit app, it reads the garage setup wrongly from the exports (rear camber / toe /
springs are read from the front-right wheel slot, camber and toe are radians clipped into degree ranges, so
the setup I actually ran is never seen), and it never asks how the car felt. Telemetry measures effects
(lap time, wear, balance), not feel, so "best setup" advice built from numbers alone optimises the stopwatch,
not the car I enjoy driving. In practice I have 15–60 minutes and no structured way to test a change,
account for tyre wear and fuel burning off during the test, and decide.

## Solution

1. **Setup reading is correct everywhere.** One reader turns the setup channels of an SRT export or of our
   own UDP recording into the setup in garage units (front/rear values, degrees, clicks, %, psi) — exactly
   what the in-game garage shows. Everything that shows, fingerprints, compares or builds setups uses it.
   Existing library sessions are re-read from their stored telemetry.
2. **A race engineer on the Live page runs an optometrist-style test during practice.** I start a program
   (short ~15–20 min or full 40–60 min). The engineer picks one setup parameter and gives me two variants
   ("1" and "2", order randomised so I don't know which one is the current baseline). I drive 2–3 laps on
   each; when I'm back in the garage it asks "1 or 2?" (plus how strongly, up to three where/what tags and an
   optional note). It corrects the lap times for fuel burn and tyre wear, shows its verdict next to mine,
   and calls out disagreements ("2 feels better but is 0.2 s/lap slower, mostly sector 3"); I decide. It
   narrows the range (big steps first, halving) or moves to the next parameter, then runs a short quali
   check on softs and finishes with a long run on the race compound. It talks to me through a text feed on
   the Live page only — no voice, no chat.

## User Stories

1. As a driver, I want the app to show my garage setup with the same numbers the in-game garage shows (e.g. camber −3.50 / −2.00, springs 38 / 4), so that I can trust every setup screen and recommendation.
2. As a driver, I want front and rear values of camber, toe, springs and ride height read from the right wheels of the export, so that rear settings are never confused with front ones.
3. As a driver, I want camber and toe converted from the export's radians to degrees, so that the values I ran are shown instead of clipped garbage.
4. As a driver, I want engine braking and ballast read as well, so that the whole garage is visible.
5. As a driver, I want the same reading for SRT CSV imports and for sessions the app recorded itself over UDP, so that both sources agree.
6. As a driver, I want my existing library sessions re-read with the corrected reader (after a backup), so that old fingerprints, setup diffs and comparisons become correct without re-importing.
7. As a driver, I want a setup change between two sessions to show as a change only when a garage value really changed, so that fingerprints don't split one setup into several.
8. As a driver, I want to start an engineer program from the Live page during practice, choosing short (≈15–20 min) or full (40–60 min), so that the test fits the time I have.
9. As a driver, I want the engineer to start from the setup currently on the car as the baseline, so that I can begin from an internet setup or my last one without typing anything in.
10. As a driver, I want camber to stay at the game meta (most negative) unless I change it myself, so that the program doesn't waste time on something everyone runs the same.
11. As a driver, I want the engineer to test one parameter at a time in the order wings → differential → anti-roll bars → springs & ride height → brakes, so that the parameters that change feel the most come first.
12. As a driver, I want each test as a pair of variants labelled "1" and "2" in random order, so that I don't favour a change just because it is new.
13. As a driver, I want the first pair to differ clearly (about 3 clicks / 3 steps) and later pairs to halve the gap, so that I can feel the difference and then fine-tune.
14. As a driver, I want a clear instruction for what to set in the garage ("Variant 2: front ARB 15"), so that I can make the change quickly.
15. As a driver, I want the engineer to detect from the car's setup which variant I am actually running, and warn me if the tested value doesn't match either variant, so that a wrong click doesn't spoil the test.
16. As a driver, I want the feed to tell me where I am in the run ("Variant 1: lap 2 of 3"), so that I know when to come in.
17. As a driver, I want out-laps, in-laps, invalid laps and laps with a big mistake excluded from the comparison, so that the verdict uses representative laps.
18. As a driver, I want the question "1 or 2?" to appear when I'm back in the garage after both variants of a pair, so that I answer while the feeling is fresh.
19. As a driver, I want to answer with 1 / 2 / no difference, a strength (slightly / clearly), up to three tags (entry / mid / exit × slow / fast corners, braking stability, braking lock-ups, traction, kerbs, confidence) and an optional sentence, so that my feel is captured in about 15 seconds.
20. As a driver, I want the lap-time comparison corrected for fuel burned and tyre wear accumulated during the test, so that the second variant isn't punished for running on older tyres and favoured for running lighter.
21. As a driver, I want the engineer to suggest a fresh tyre set for a variant when I have spare sets, and otherwise continue on the current set with the correction, so that the test stays fair without wasting sets I need for quali and the long run.
22. As a driver, I want the engineer's own verdict (pace delta per lap, its confidence and the noise level) shown next to mine, so that I see what the stopwatch says.
23. As a driver, I want an explicit call-out when my feel and the stopwatch disagree, including the sectors where the difference is, so that I can decide knowingly — the choice stays mine.
24. As a driver, I want to confirm which variant wins (defaulting to my answer), so that the winner becomes the new baseline.
25. As a driver, I want a parameter to be settled after two consecutive "no difference" answers or when the step is down to one click, so that the program moves on instead of chasing noise.
26. As a driver, I want to skip a parameter or end the balance phase early, so that I stay in control.
27. As a driver, I want the program to keep enough time for the quali check and the long run and tell me when it moves on ("ending balance, quali check next"), so that the session always produces both.
28. As a driver, I want a quali check: the final setup and the session's starting setup on softs with low fuel, two flying laps each when time allows, so that I know the race-oriented setup doesn't cost too much over one lap.
29. As a driver, I want the parc fermé rule applied: race pace counts 70%, quali 30%, and the engineer proposes reverting the last change when the combined score gets worse, so that one setup works for both.
30. As a driver, I want a long run of 8–10 laps on the race compound at the end, with pace and wear per lap reported, so that the race strategy gets a real long run (this is what was missing when stints came out too short).
31. As a driver, I want the long run to be stored like any other recorded session lap data, so that the tyre model and strategy pick it up automatically.
32. As a driver, I want the engineer to remember per track which parameters were settled and at which values, so that next time it starts from them and skips what's already tested.
33. As a driver, I want the whole test (pairs, laps used, corrections, my answers, verdicts, final setup) saved, so that I can look back at it later.
34. As a driver, I want the engineer state to survive a page reload or a second browser tab, so that refreshing the Live page doesn't lose the test.
35. As a driver, I want the engineer card to fit the portrait 1080×1920 Live layout without hiding timing and tyres, so that it works on my second monitor.
36. As a driver, I want the program to stop cleanly when the session ends or I leave practice, with what was decided so far saved, so that nothing is lost.
37. As a driver, I want the engineer to refuse to start outside practice sessions or in wet conditions (and say why), so that it never gives a race or wet-weather setup call by mistake.

## Implementation Decisions

### Step 1 — Setup reading

- **One reader, one canonical shape.** A pure function in the `telemetry` package turns raw setup channels
  (SRT naming: per-wheel arrays `_0.._3` front-first FL, FR, RL, RR; angles in radians; pressures in Pa;
  percentages as 0–1 fractions) into the canonical *garage setup*: the existing garage keys of the setup
  parameter table, where paired parameters use `_0` = front and `_1` = rear (camber, toe, springs, ARB,
  wings), ride heights and tyre pressures stay per wheel (FL, FR, RL, RR), plus engine braking and ballast.
  Camber/toe are converted to degrees. Values are never clipped: an out-of-range value is a reading error to
  surface, not to hide.
- Mapping rule for per-wheel → front/rear: front = index 0 (FL), rear = index 2 (RL); if left and right
  differ, the reader reports it rather than averaging silently.
- Both inputs go through it: an SRT export frame (median of the stable non-reset rows of a lap or session, as
  today) and our UDP recording (whose recorder already writes SRT-convention setup channels — keep the
  recorder as is).
- The setup parameter table's ranges stay the garage ranges in garage units; normalisation no longer clips
  raw export values into those ranges.
- Every consumer (setup fingerprints and diffs, track baselines, setup builder, setup evaluation, setup log,
  Streamlit garage screens until retired) reads setups only through this reader. The live engine reads the
  car's current setup from the CarSetups packet through the same reader (via the recorder's row mapping).
- **Library repair:** a one-off, idempotent upkeep step re-derives each session's stored setup and setup
  fingerprint from its stored telemetry, after a backup of the database (same pattern as the existing
  backups under `data/backups`). Sessions whose telemetry has no setup channels keep their stored setup.

### Step 2 — Engineer (optometrist test)

- **Engineer module (the seam):** a deep, pure, I/O-free module in the server's live package (or the
  `telemetry` package) with a small interface:
  - `start(program, baseline_setup, track, now)` — program = short | full with a time budget in minutes;
  - `on_lap(lap)` — one completed lap: lap number, time, validity, in/out/pit flags, sector times, fuel at
    start and end, compound, tyre set index and whether it was fresh, tyre age, max-wheel wear, garage setup;
  - `on_garage(in_garage: bool)` and `on_tyre_sets(sets)` — garage presence and the TyreSets list;
  - `answer(verdict, strength, tags, note)`, `confirm(winner)`, `skip()`, `end_phase()`, `stop()`;
  - `view()` — the serialisable state the UI renders: phase, current parameter, the two variants (values
    and which one is "1"), the instruction, run progress, the pending question, verdict history, feed
    lines, time budget left.
  The live engine only adapts packets into these calls; all decisions live in the module.
- **Program and phases:** balance (≈60% of the budget) → quali check (≈15%) → long run (≈25%), ending
  earlier phases when the remaining time only covers what's left. Short program tests one parameter;
  full tests 2–3.
- **Parameter order and steps:** wings (front first) → diff on/off-throttle → ARB front/rear →
  springs & ride height → brake bias/pressure. Camber is not tested (meta), toe is not tested in this spec.
  First pair is baseline vs baseline ± a clear step (≈3 clicks / steps for that parameter, direction chosen
  from the parameter's typical effect and the last telemetry diagnosis when available, else +), then the gap
  halves around the winner down to the parameter's smallest step. Settled after two consecutive "same"
  answers or at the smallest step.
- **Randomisation:** which value is shown as "1" is random per pair (seedable for tests) and recorded.
- **Variant detection:** the run's variant is identified from the tested parameter's value in the car's
  current garage setup; a mismatch produces a feed warning and the laps are not counted for either variant.
- **Laps used:** valid flying laps only (no out/in/pit laps, no invalid laps, no lap slower than the run
  median by more than a mistake threshold). 2–3 laps per variant.
- **Correction:** each lap time is corrected to a common fuel load with the library fuel effect and to a
  common tyre age with a degradation slope — measured within the session on the same set when there are
  enough laps, else the track compound model's degradation for that compound. The verdict is the corrected
  mean difference with a noise estimate (spread of the corrected laps); below the noise it is "no measurable
  difference". The setup evaluation's noise floors are the prior art.
- **Fresh vs used set:** from the TyreSets packet the engineer suggests a fresh set for the second variant
  when spare sets exceed what the quali check and the long run need; otherwise it continues and relies on
  the correction (and says so).
- **Feel vs stopwatch:** when my answer and the corrected verdict disagree (or agree only below noise), the
  feed states it with the per-sector corrected deltas. Corner/phase-level comparison is not in this spec.
- **Parc fermé score:** race pace (balance-phase pairs on the race compound) weighs 70%, quali (soft, low
  fuel pair in the quali check) 30%; if the final setup's combined score is worse than the session's starting
  setup the engineer proposes reverting the last accepted change; I confirm.
- **Persistence:** a new library table stores engineer tests (track, date, program, baseline, each pair with
  values, laps used, corrections, my answer, the stopwatch verdict, the winner) and per-track settled
  parameter values used as the starting point next time. The long run is stored by the existing session
  recorder like any lap data.
- **Live server integration:** the live engine feeds the module from LapData (lap completion, validity,
  driver status = in garage), Session (session type, weather), CarStatus (fuel, compound, tyre age),
  CarDamage (wear), CarSetups (garage setup through the step-1 reader) and TyreSets. The module only runs
  in practice sessions in dry conditions; elsewhere `start` refuses with a reason.
- **API contract:** the existing one-way `/ws/live` stream carries the engineer `view()` inside the
  snapshot (key `engineer`, `null` when no program) and feed lines as events of kind `engineer`. Commands are
  REST: `POST /api/live/engineer/start {program: "short"|"full", minutes?}`, `POST /api/live/engineer/answer
  {verdict: "1"|"2"|"same", strength: "slight"|"clear", tags: string[] (≤3), note?}`,
  `POST /api/live/engineer/confirm {winner: "1"|"2"}`, `POST /api/live/engineer/skip`,
  `POST /api/live/engineer/next-phase`, `POST /api/live/engineer/stop`; each returns the new `view()`; 409 with
  a reason when not allowed. Same access-token rule as the live socket.
- **Live page:** an Engineer card in the portrait layout: current instruction and run progress, the last
  few feed lines, the question form (1 / 2 / same, slightly / clearly, tag chips limited to three, optional
  note) shown when a question is pending, and start / skip / next phase / stop controls. UI text in English.
  Text only.

## Testing Decisions

- Good tests exercise external behaviour at the two agreed seams only, not internals.
- **Seam 1 — setup reader:** given the real local Miami exports in the repo root (FP, Q, Race; skip when
  absent, like the existing library-dependent tests) the reader returns the in-game garage values: front
  wing 25, rear wing 20, camber −3.50 / −2.00, toe 0.01 / 0.12, springs 38 / 4, ARB 6 / 14, ride height
  21 / 48, diff 100 / 20 %, brake pressure 99 %, bias 56 %, engine braking 50 %, ballast 6, pressures
  ≈26.0 / 22.7 psi. The same values come out of our UDP recording of a session (recorder output from the local
  capture, as the recorder tests do), plus a synthetic-row unit test that needs no local files. Library
  repair: a tmp library with a stored wrong setup is repaired, idempotently, with a backup. Existing setup
  tests (setup log, builder, history) keep passing after their fixtures move to garage units.
- **Seam 2 — engineer module:** scenario tests feed synthetic lap sequences and answers and assert on
  `view()`: a pair produces a question only after both variants have counted laps and the car is in the
  garage; randomisation is reproducible with a seed; a wrong garage value produces a warning and no counted
  laps; fuel and tyre-age correction flips a raw-time verdict when the second variant ran lighter on
  older tyres; below-noise differences read as "no measurable difference"; disagreement call-outs; halving
  and the two-"same" stop rule; time-budget phase transitions; parc fermé revert proposal; refusal outside
  practice / in the wet; persistence round trip on a tmp library and the next program starting from settled
  values.
- **Integration (no new seam):** the existing capture-replay engine test keeps passing with the module
  wired in; an API test (FastAPI TestClient, like `tests/server/*`) checks start → answer → stop and the 409
  paths; frontend pure helpers (if any, e.g. a view-to-card mapping) get vitest tests like `src/lib/*.test.ts`;
  the Live card is checked in a real browser at 1080×1920 (sandbox data copy + headless Chrome, as before).

## Out of Scope

- Voice (text-to-speech), chat with the engineer, sounds.
- Corner- and phase-level (entry/mid/exit) comparison of the two variants — comes with step 3 (front-first
  wheel fix, g-force axes, lap/corner comparison views in the new app).
- The front/rear wheel-order fix for tyre temperatures/pressures/wear, lock-ups and g-force axes (step 3).
- Setup duel of internet setups (step 4) and computing a setup from scratch (step 5).
- Porting the remaining Streamlit setup screens; retiring Streamlit.
- Testing camber and toe; carrying settled values across tracks of a similar type.
- Race and wet-weather sessions.

## Further Notes

- The project is local-only: commit locally, never push.
- Decisions come from a grilling session on 2026-10-14: goal is race pace and tyre life (b), motivation is
  enjoying telemetry (d), parc fermé weighting 70/30, camber stays meta, A–B with correction (fresh set when
  available) rather than A–B–A, test on both race compound and quali trim, practice can run 40–60 min.
- The user boxes at ~62% median / 70% p75 max-wheel wear; races are always 50% distance.
