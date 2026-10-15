Status: ready-for-agent

# Setup duel: 2–3 setups, a few laps each, ranked on my race pace, tyre life and balance (roadmap step 4)

## Problem Statement

When I arrive at a track I usually start from a setup found on the internet, and there are several of them.
I have no fair way to decide which one suits me: the one I drove last always feels better or worse for
reasons that have nothing to do with the setup (fuel burned off, tyres older, track rubbering in), and the
"fastest lap" of each tells me little about a 50 % race where tyre life matters. The optometrist test
(step 2) tunes one parameter at a time from a baseline, but it needs a good baseline to start from — and I
have nowhere to keep "the setup for this track" once I know it. I also have sessions in the library where I
already drove several setups, but nothing compares them.

## Solution

A **setup duel** ranks 2–3 complete setups on my own driving and makes the winner the **track baseline**.

- **Live, in practice (Engineer card, program "Duel"):** I choose 2 or 3 contestants and optionally name
  them ("Internet A", "my Monza"). For each one the engineer says "Load setup A in the garage and drive 3–5
  laps". It recognises the setup from the game's setup packet when I leave the garage (no typing): the first
  new mechanical setup becomes A, the next B, and so on; it warns when I drive a setup it already has. It
  counts clean laps per contestant (like the engineer: no in/out/pit/invalid laps, no big mistakes), suggests
  a fresh tyre set per contestant when spare sets exist and otherwise corrects for tyre age, and corrects for
  fuel. When every contestant has enough laps and I'm back in the garage, it asks me to rank them by feel
  (drag order or 1st/2nd/3rd, optional note), then shows its ranking with the numbers and I confirm the
  winner.
- **Offline, from the library (a "Setups" page per track):** the app lists the distinct setups I have
  driven on the track (by mechanical fingerprint) with their runs. I pick 2–3 and it ranks them with the
  same rules, but only on comparable runs (same conditions, same compound family, ≥ 3 clean laps each,
  fuel-corrected, outside the noise band); otherwise it says why they are not comparable. I can name a
  setup.
- **Ranking:** a race-time estimate per lap for each contestant: 70 % race pace (fuel- and tyre-age-
  corrected mean of clean laps, plus the cost of its tyre wear rate over a 50 % race through the existing
  strategy model) and 30 % one-lap pace (best corrected lap) — the parc fermé weighting already agreed.
  Differences inside the noise band are "no measurable difference"; then balance (distance from neutral per
  phase, from step 3's slip-angle balance) and my feel decide, in that order, and the app says so. My feel
  ranking is shown next to the stopwatch ranking with call-outs when they disagree; I confirm the winner.
- **Track baseline:** the confirmed winner is stored as the track's baseline setup (garage units, its name,
  where it came from, the duel it won). The Setups page shows it with a copy-friendly list of garage values
  to type into the game; the engineer's optometrist test and the step-5 generator use it as the starting
  point. A later duel or a finished engineer test can replace it (the engineer's final setup is offered as
  the new baseline).

## User Stories

1. As a driver, I want to start a duel from the Engineer card in practice with 2 or 3 contestants, so that I can compare internet setups in one session.
2. As a driver, I want to name each contestant optionally, so that I remember where a setup came from.
3. As a driver, I want the app to recognise which setup I loaded from the game's own setup data when I leave the garage, so that I never type setup values.
4. As a driver, I want the first new setup to become contestant A, the next B and so on, so that loading them in order is all I need to do.
5. As a driver, I want a warning when I drive a setup that is already a contestant or a setup that differs only in fuel or pressures, so that I don't waste laps.
6. As a driver, I want a clear instruction for what to do now ("Load setup B, drive 4 laps"), so that I always know the next step.
7. As a driver, I want 3–5 counted laps per contestant (out/in/pit/invalid laps and big mistakes excluded), so that each setup is judged on representative laps.
8. As a driver, I want a fresh tyre set suggested per contestant when I have spares and a tyre-age correction otherwise, so that the comparison is fair.
9. As a driver, I want lap times corrected for fuel, so that the setup driven last isn't favoured for being lighter.
10. As a driver, I want to rank the contestants by feel when I'm back in the garage after the last one, so that my opinion counts before I see the numbers.
11. As a driver, I want the app's ranking with race pace, one-lap pace, wear per lap, balance per phase and the noise level, so that I see why one setup wins.
12. As a driver, I want race pace weighted 70 % and one-lap pace 30 %, so that the ranking matches the 50 % races I actually race.
13. As a driver, I want tyre wear turned into race time through the strategy model, so that a fast setup that eats tyres is judged by what it costs over a race.
14. As a driver, I want "no measurable difference" when the gap is inside the noise, with balance and then my feel deciding, so that noise doesn't pick the winner.
15. As a driver, I want call-outs when my feel and the stopwatch disagree, so that I decide knowingly.
16. As a driver, I want to confirm the winner, so that the decision stays mine.
17. As a driver, I want to stop a duel early and still keep what was measured, so that a short session isn't wasted.
18. As a driver, I want a Setups page per track listing the distinct setups I've driven with their runs, so that I can compare setups after the fact.
19. As a driver, I want to pick 2–3 of those setups and get the same ranking, so that old sessions are useful.
20. As a driver, I want the offline duel to refuse incomparable runs (wet vs dry, different compound family, too few clean laps) and tell me why, so that I don't trust a meaningless verdict.
21. As a driver, I want to name a setup in the library, so that I recognise it next time.
22. As a driver, I want the winner stored as the track baseline, so that next time I know what to load.
23. As a driver, I want the baseline shown as a list of garage values in the game's order and units, so that I can type it into the game quickly.
24. As a driver, I want the engineer's optometrist test to start from the baseline's settled values and to offer its final setup as the new baseline, so that tuning builds on the duel.
25. As a driver, I want every duel stored with its contestants, laps, ranking and my feel, so that I can look back.
26. As a driver, I want the baseline history per track, so that I can go back to an older baseline.

## Implementation Decisions

- **Prefactor — shared lap correction:** the engineer's fuel / tyre-age correction, noise estimate and
  "counted lap" rules move to a small pure module both the engineer and the duel use (no behaviour change;
  existing engineer scenario tests stay green).
- **Duel module (pure, I/O-free, like the engineer):** `start(n, names, baseline_setup, track, session_type,
  wet, now, models)`, `on_lap(EngineerLap)`, `on_garage`, `on_tyre_sets`, `on_tick`, commands `rank(order,
  note)`, `confirm(winner)`, `skip_contestant`, `stop`; `view()` JSON for the card; `result()` for
  persistence. Contestants are identified by the mechanical fingerprint (existing `mech_fingerprint`, which
  ignores fuel / brake-bias balance / compound); pressure-only differences count as the same setup and
  trigger the warning. Laps per contestant: target 4, min 3, max 5. Practice only, dry only (same refusal
  rules as the engineer).
- **One live program at a time:** the live engine routes REST commands to whichever program is active
  (engineer or duel); starting one while the other runs is refused (409). New endpoints `POST
  /api/live/duel/{start|rank|confirm|skip|stop}`; the snapshot carries `duel` (null when idle) next to
  `engineer`; feed lines go out as events of kind `engineer` (same feed on the card).
- **Ranking (pure, shared by live and offline):** input = per-contestant clean laps (corrected times, wear
  per lap, optional corner profiles from step 3); output = per contestant `{race_pace_s, quali_pace_s,
  wear_pct_per_lap, race_cost_s (via the strategy optimiser for a 50 % race with the contestant's pace
  offset and wear rate on the race compound), score_s (0.7 race + 0.3 quali, per lap), balance {entry, mid,
  exit}, n_laps}` plus pairwise `measurable` vs a noise band (floor 0.10 s/lap), the order, the tie-break
  used ("stopwatch" | "balance" | "feel") and call-out texts. When the strategy model is unavailable for the
  track, race cost falls back to pace + wear × a fixed seconds-per-%-per-lap factor and says so.
- **Offline duel:** candidates = runs from the existing run splitter over all sessions of the track, grouped
  by mechanical fingerprint, filtered by conditions state and compound family, ≥ 3 clean laps; balance from
  step 3. `GET /api/tracks/{track}/setups` (candidates with runs and names), `POST
  /api/tracks/{track}/duel {fingerprints: [...]}` (ranking or a "not comparable" reason per pair),
  `PUT /api/setups/{fingerprint}/name`.
- **Storage:** new tables `setup_names (fingerprint, track, name, source, updated_at)`, `duels (id, track,
  mode live|offline, started_at, result_json)`, `track_baselines (id, track, setup_json, fingerprint, name,
  source duel|engineer|manual, ref_id, created_at, active)` — one active row per track, history kept.
  `GET /api/tracks/{track}/baseline`, `POST /api/tracks/{track}/baseline` (from a duel winner, an engineer
  test's final setup, or a library session's setup).
- **Engineer link:** when the engineer finishes, its final setup is offered as the new baseline (a
  `baseline_offer` in its view; accepting calls the baseline endpoint). The engineer still starts from the
  car's current setup; the Setups page tells me to load the baseline first.
- **React:** Engineer card gets the "Duel" start option (2 or 3, optional names), a duel run panel
  (contestants with laps counted / target, current instruction, detected setup), the feel-ranking form and
  the ranking table; a new top-level **Setups** page (per track, reachable from the library and the session
  page) with the baseline card (garage values in game order and units, source, history), the candidate
  list with names and runs, and the offline duel picker + result. UI text in English.

## Testing Decisions

- External behaviour only, at these seams: (1) the duel module's `view()` driven by synthetic laps and
  commands (scenario tests like the engineer's); (2) the ranking function on synthetic contestants (weights,
  noise band, tie-breaks, wear cost) and on real library runs of a track with several setups (skip when the
  library is absent); (3) the HTTP API with FastAPI TestClient on a tmp library (setups list, offline duel
  incl. "not comparable", naming, baseline set / history, live duel start → stop and the 409 when the
  engineer runs); (4) the existing engineer scenario tests and the capture-replay engine test stay green
  after the prefactor.
- Frontend pure helpers (ranking rows, garage-value list ordering, form validation) get vitest tests; the
  Setups page and the Engineer card duel panels are checked in headless Chrome on a sandbox library copy
  (card at 1080×1920).

## Out of Scope

- Typing setups into the app as a form (setups come from the game or the library).
- Importing setup files from websites.
- Duels in races or the wet.
- Generating a setup (step 5 — it consumes baselines and duels).

## Further Notes

- Local-only: commit locally, never push.
- The user asked for both live (from the game's packets) and offline (library) duels (2026-10-15).
- Depends on step 3's front-first wheels and slip-angle balance for the balance column; without step 3
  the balance column is omitted.
