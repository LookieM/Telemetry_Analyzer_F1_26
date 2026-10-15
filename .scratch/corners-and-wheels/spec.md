Status: ready-for-agent

# Correct wheels and g-forces, Corners view, corner/phase A/B for the engineer (roadmap step 3)

## Problem Statement

The analysis side of the app still mislabels the car. SRT exports store every per-wheel array front-first
(0=FL, 1=FR, 2=RL, 3=RR — verified against our own UDP recording of the same Miami sessions), but the
analysis code, the Tyres tab and the React app read them as RL, RR, FL, FR. So the front-left tyre is shown
as rear-left, "limiting wheel RL" really means the front-left, the hot-pressure targets for the front are
compared with the rear tyres, and "front lock-ups" are rear lock-ups. The g-forces are wrong too: the stored
"lateral g" is really the longitudinal axis (it correlates 0.86–0.89 with the brake in every library
session) and the stored "longitudinal g" is vertical. Anything built on them (turn-in detection, the GG
plot) is wrong.

On top of that, I cannot answer the question I care about most after a session: where on the lap do I lose
time, and why? The React app has a lap comparison (traces, delta, sectors, mini-sectors) but no corner view;
the old Streamlit corner table used catalogue corner windows that do not line up with the real corners
(brake points outside the corner, "exit +135 km/h" artefacts) and a temperature-based "balance" that says
understeer on every lap. And the live race engineer compares two setup variants only by lap and sector
time, so it can say "2 is 0.15 s/lap faster in S3" but not "2 is faster on exit of the slow corners and the
rear slides less there", which is what a setup change is meant to do.

## Solution

1. **Right wheels, right axes everywhere.** One front-first wheel order for exports (FL, FR, RL, RR) used by
   the channel registry, the loader, lock-up detection, tyre stints/targets, the Tyres tab and the React
   app; the live engine keeps the UDP order (RL, RR, FL, FR) it already handles correctly. Lateral g =
   `gforce_Y`, longitudinal g = −`gforce_X` (positive = accelerating), vertical g = `gforce_Z`. The library
   is repaired once (after a backup): stored derived columns are recomputed or swapped, and sessions that
   never stored the lateral axis (the old compact imports #1–#20) say "lateral g not recorded" instead of
   showing wrong data.
2. **Corners from the data, per track.** Corners are detected from a reference lap of the track (braking or
   lift → minimum speed → back to full throttle), merged when there is no full throttle between them,
   named from the track catalogue by nearest apex (T1, T2–T3 …), and stored per track so every session of
   that track uses the same corners. They can be rebuilt.
3. **A Corners tab in the React session page: "Where and why do I lose time?"** One row per corner with
   time in the corner from the aligned delta (corner times add up to the lap delta), entry / minimum /
   exit speed, brake point, trail-brake length and full-throttle point, each with its difference to the
   reference (best lap of the session, another lap, or a lap of another session of the same track).
   Balance per corner and phase (entry / mid / exit) from the slip angles (front minus rear, positive =
   understeer), traction on exit (rear wheel slip on throttle) and lock-ups per wheel. Clicking a corner
   zooms the map and the traces to it with brake / throttle markers. Corners are tagged slow / medium /
   fast. Sentences only from measured differences above the noise ("T4: brake 12 m earlier, vmin −6 km/h,
   −0.08 s").
4. **Lap comparison shows the right channels.** The Laps tab can add g-forces (lateral / longitudinal) and
   per-wheel channels (slip angle, slip ratio, tyre temps) to the trace with correct wheel labels.
5. **The engineer compares variants corner by corner.** For every counted lap the live engine keeps the
   lap's distance-binned frame from the recorder and turns it into a corner profile; the engineer averages
   the profiles per variant and adds the per-corner / per-phase time and balance differences to its result
   ("Variant 2: +0.06 s entry T1, −0.11 s exit T10–T11; rear slip on exit −0.4°"), and checks my tags against
   them (I said "exit slow corners", the stopwatch agrees/disagrees there).

## User Stories

1. As a driver, I want the tyre temperatures, pressures, wear and brake temperatures of each wheel labelled with the wheel they really belong to, so that I don't change the wrong corner of the car.
2. As a driver, I want "limiting wheel" in the Tyres tab to name the tyre that really wears fastest, so that I know which corner to protect.
3. As a driver, I want the hot-pressure targets for the front compared with the front tyres and the rear targets with the rear tyres, so that the cold-pressure advice is right.
4. As a driver, I want front and rear lock-ups counted on the right axle, so that brake-bias advice points the right way.
5. As a driver, I want lateral and longitudinal g read from the right export axes, so that turn-in detection and g-force traces are physically right.
6. As a driver, I want my existing library sessions repaired once with a backup first, so that I don't have to re-import anything.
7. As a driver, I want sessions that never recorded lateral g to say so instead of showing a wrong trace, so that I don't draw conclusions from missing data.
8. As a driver, I want the car layout in every view (FL FR on top, RL RR below) to stay the same while the data behind it is corrected, so that the screens look familiar.
9. As a driver, I want corners detected from my own driving on each track, so that the corner windows line up with where I really brake, turn and accelerate.
10. As a driver, I want corners named like the real circuit (T1, T4, T9–T10) where the catalogue knows the track, and numbered from the start line otherwise, so that I can talk about them.
11. As a driver, I want compound corners merged when I never reach full throttle between them, so that one complex is one row.
12. As a driver, I want the same corners for every session of a track, so that corner times are comparable across sessions.
13. As a driver, I want to rebuild a track's corners from a better lap, so that a bad first reference does not stick forever.
14. As a driver, I want a Corners tab in the session page, so that corner analysis lives in the new app.
15. As a driver, I want the time spent in each corner compared with a reference so that the corner deltas add up to the lap delta, so that I see exactly where the lap time went.
16. As a driver, I want entry, minimum and exit speed, brake point, trail-brake length and full-throttle point per corner with their differences to the reference, so that I see why I lost the time.
17. As a driver, I want the reference to default to the session's best lap and be switchable to another lap or a lap from another session of the same track, so that I can compare against my PB.
18. As a driver, I want the corners sorted or highlighted by time lost, so that the biggest losses come first.
19. As a driver, I want to click a corner and have the map and traces zoom to it with brake and throttle markers, so that I can see the cause.
20. As a driver, I want each corner tagged slow / medium / fast by its minimum speed, so that balance and setup advice can separate mechanical from aero corners.
21. As a driver, I want short sentences only where a measured difference is above the noise, with the numbers in them, so that I'm not told generic things.
22. As a driver, I want the car's balance per corner and phase (entry / mid / exit) measured from front vs rear slip angle, so that "understeer on entry of slow corners" is measured rather than guessed from temperatures.
23. As a driver, I want a one-line balance summary for the lap ("entry neutral, mid slight understeer in slow corners, exit oversteer T3/T4"), so that I get the picture at a glance.
24. As a driver, I want traction on exit measured from rear wheel slip on throttle, so that I can see where the rear spins up.
25. As a driver, I want lock-ups counted per wheel with where they happened, so that I know which corner and which tyre.
26. As a driver, I want balance averaged over the session's clean laps as well as for the selected lap, so that one mistake doesn't define the car.
27. As a driver, I want a clear "not enough data" message when a session lacks slip angles or clean laps, so that empty numbers are explained.
28. As a driver, I want to add lateral / longitudinal g and per-wheel slip angle, slip ratio and tyre temperatures to the lap-comparison trace, so that I can inspect the cause of a corner loss myself.
29. As a driver, I want the engineer to show, after a pair, in which corners and phases variant 2 gained or lost time versus variant 1 (fuel- and tyre-corrected laps averaged per variant), so that I see what the setup change did on track.
30. As a driver, I want the engineer to show how the balance moved per phase between the variants (front minus rear slip), so that I can relate my feel to a measurement.
31. As a driver, I want my tags (e.g. "exit · slow corners") checked against the corner/phase deltas ("you said exit of slow corners is better with 2: the stopwatch agrees, −0.09 s over T3, T10"), so that the comparison speaks my language.
32. As a driver, I want the corner/phase comparison to fall back to the sector comparison when the corner profile is missing (not enough counted laps with a full frame), so that the engineer still works.
33. As a driver, I want the corner comparison stored with the engineer test, so that I can look back at what a change did.

## Implementation Decisions

- **Wheel order (exports):** a single front-first constant (FL, FR, RL, RR) in the channel registry is the
  only definition; the loader's tyre labels, the car layout indices, the per-wheel lock-up split (front =
  indices 0, 1; rear = 2, 3), the tyre targets' front/rear choice, the tyre module docstring and the old
  insights / plots helpers that hard-code labels all derive from it. The live engine's UDP order constant is
  untouched (it is correct for UDP). The React app's wheel constant becomes front-first; colours stay per
  label so FL keeps its colour.
- **G-force axes (exports):** lateral = `gforce_Y`, longitudinal = −`gforce_X`, vertical = `gforce_Z`;
  `g_mag` is the planar magnitude. The vertical-g registry alias changes from `gforce_Y` to `gforce_Z`.
  Turn-in detection keeps using |lateral g| (now the right channel).
- **Library repair (one-off, flagged in `library_meta`, idempotent, backup first):** for each session's
  parquet, written atomically (temp file + replace), after copying every parquet it will touch and the
  database into `data/backups/<timestamp>-before-wheel-axes-fix/`:
  - sessions with raw `gforce_*`: recompute `g_lat`, `g_long`, `g_mag` from them;
  - sessions without (compact imports): `g_long` = −stored `g_lat` (it was −longitudinal), `g_lat` and
    `g_mag` set to missing;
  - `lockup_front` and `lockup_rear` are swapped (the detector is symmetric, so this equals recomputing);
  - per-wheel raw arrays are not touched (only their labels were wrong);
  - the laps table summary columns that depend on lock-ups are recomputed if any exist.
  It runs at server start like the setup re-read. The report counts repaired / skipped sessions.
- **Corner detection (new pure module, deep):** input = one reference lap frame (distance, speed, throttle,
  brake, lap time, optional steering / lateral g) and the track's catalogue entry (optional); output =
  ordered corners `{id, name, start_m, end_m, apex_m, vmin_kmh, speed_class "slow|medium|fast", merged_from}`.
  Rules: a corner starts at braking onset or a throttle lift (< 95 %) before a speed minimum, ends where
  throttle returns to ≥ 95 % (or at the next corner's start); two minima without full throttle between them
  are one corner; minima with < 3 km/h dip and no brake are not corners (flat kinks). Speed classes:
  slow < 120 km/h, medium 120–200, fast > 200 (vmin). Names: nearest catalogue apex within a tolerance,
  merged names joined with "–"; unknown tracks get T1..Tn. Straights are not rows.
- **Per-track corner storage:** a new `track_corners` table keyed by the canonical track name, holding the
  JSON corner list, the source session/lap and the build time. Built lazily on first request from the
  track's best clean lap in the library; a rebuild command picks a given session/lap.
- **Corner analysis (pure, deep):** `corner_report(focus_lap, ref_lap, corners)` → per corner: time in
  corner (focus, ref, delta from the aligned delta at the boundaries, so deltas sum to the lap delta within
  0.02 s), entry speed (at start), vmin, exit speed (at end), brake point, trail-brake length (m and s),
  full-throttle point, each with ref value and difference; plus phase boundaries (entry = start → vmin
  − mid window, mid = vmin ± window, exit = mid end → end). Callout sentences from fixed rules with
  thresholds (e.g. brake point ≥ 5 m, speed ≥ 3 km/h, time ≥ 0.03 s).
- **Balance (pure, deep):** per corner and phase: understeer index = mean |slip angle front| − mean |slip
  angle rear| in degrees, over samples with |lateral g| > 0.5 or steering above a small threshold; traction
  = mean rear |slip ratio| while throttle > 50 % in the exit phase; lock-ups per wheel = runs of slip ratio
  < −0.15 with brake > 0.2, with distance. Session view = median over clean laps (push / clean class,
  existing lap classes). Sessions without slip channels return `available: false` with a reason. The old
  temperature-based balance is not used by the new app.
- **API (server):** `GET /api/sessions/{id}/corners?lap=&ref_lap=&ref_session=` → `{track, corners:
  [definition + metrics + ref + deltas + balance + callouts], lap_delta, sum_corner_delta, balance_summary,
  lockups: [{wheel, distance_m, corner}], reference: {session, lap}}`; `GET /api/sessions/{id}/balance` →
  per-corner/phase medians over clean laps + summary; `POST /api/tracks/{track}/corners/rebuild {session,
  lap}`. The existing compare and lap-channel endpoints accept the new channels (g_lat, g_long, per-wheel
  slip angle / slip ratio / tyre temps) and return wheel-labelled series.
- **React Corners tab:** a new session tab between Laps and Tyres. Reference selector shared with the Laps
  tab's semantics; the corner table (sortable, losses coloured); a phase × corner balance heat strip; the
  map and the trace (existing `TrackMap` / `TraceChart`, shared cursor) zoom to a clicked corner with brake
  and throttle markers; "not enough data" messages. UI text in English.
- **Laps tab:** a channel picker adds g and per-wheel channels as extra panes; per-wheel series labelled
  FL / FR / RL / RR correctly.
- **Engineer corner/phase A/B:** the live ingest hands the engine each completed lap's distance-binned frame
  from the recorder (already in SRT columns); a pure function turns it into a corner profile (per corner:
  time, per phase time, understeer index, rear slip on exit) using the track's stored corners (built from
  the live lap if the track has none yet). `EngineerLap` carries the optional profile. The engineer
  averages profiles per variant after the same fuel/tyre correction share (time corrections are spread over
  the lap by distance fraction) and adds to `last_result`: `corners: [{corner, phase, delta_s, understeer_delta_deg,
  traction_delta}]` (largest first, top 5) and `tag_check: [{tag, delta_s, agrees}]` mapping its tags
  (entry/mid/exit × slow/fast, traction, braking) to the matching corner groups. History and the stored
  test record keep them. The Engineer card shows the top rows under the stopwatch line.

## Testing Decisions

- Good tests check behaviour at the agreed seams only (inputs → outputs), not internals; library-dependent
  tests skip when `data/` is absent, like the existing ones; nothing writes to the real library.
- **Seam 1 — loading a session frame (`telemetry` loader + library repair):** synthetic SRT rows with known
  per-wheel values and g axes come out labelled FL/FR/RL/RR correctly with the right g signs; lock-ups land
  on the right axle; the repair on a tmp copy of a real library session (one compact, one full export)
  produces the expected columns, is idempotent and leaves a backup. Tyres stints on a real race session name
  the limiting wheel consistently with the per-wheel wear columns.
- **Seam 2 — corner analysis (pure functions):** on real sessions of Austria, Hungaroring, Monza and Miami
  (skip when absent): every brake point lies inside its corner window; vmin ≤ entry and exit speed;
  corner deltas sum to the lap delta within 0.02 s; corner count is stable between two clean laps of the
  same session; known complexes merge. Balance: understeer index sign flips between deliberately chosen
  synthetic frames; on Austria Q1 vs Q2 (diff on-throttle 55 → 80 %) the exit-phase metric moves; if it
  does not, the metric is not shown (decision recorded in the ticket).
- **Seam 3 — HTTP API (FastAPI TestClient, like `tests/server/*`):** shape of `/corners` and `/balance`,
  404/422 paths, rebuild endpoint, compare/lap-channel endpoints returning the new channels.
- **Seam 4 — engineer module (existing scenario tests):** synthetic laps with corner profiles produce
  `corners` and `tag_check` in `last_result`; missing profiles fall back to sectors; persistence round trip.
- **Frontend:** pure helpers (corner table rows, balance colours, zoom ranges, wheel labels) get vitest
  tests like `src/lib/*.test.ts`; the Corners tab and the Engineer card are checked in headless Chrome on a
  sandbox copy of the library (CDP routine), the Live card at 1080×1920.

## Out of Scope

- Energy / ERS tab, Setup & stints tab, Debrief, Track page, navigation and retiring Streamlit (phase 5
  steps 5.3–5.7).
- Re-labelling inside the old Streamlit screens beyond what follows from the shared constants.
- Setup duel (step 4) and computing a setup (step 5).
- Live corner view on the Live page (only the engineer's result uses corners live).
- Library-wide "best corner ever" / theoretical best across sessions (Track page later).

## Further Notes

- Local-only project: commit locally, never push.
- Verified facts this spec relies on: SRT per-wheel arrays front-first; SRT `gforce_X` = −longitudinal,
  `gforce_Y` = lateral, `gforce_Z` = vertical; compact imports #1–#20 have no `gforce_*` / slip channels
  (their stored `g_lat` is −longitudinal, their stored `g_long` is vertical); full exports #21+ have both.
- The plan file's phase 5.0–5.2 notes are the origin of the corner and balance rules.
