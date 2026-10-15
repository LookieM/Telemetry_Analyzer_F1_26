# 03: Balance per corner and phase from slip angles, traction and per-wheel lock-ups

**What to build:** the Corners tab shows the car's balance per corner and phase (entry / mid / exit) measured as front minus rear slip angle (positive = understeer), traction on exit from rear slip on throttle, and lock-ups per wheel with where they happened — for the selected lap and as the median over the session's clean laps — plus a one-line balance summary. Sessions without slip channels say so. See spec: Solution 3, Implementation Decisions "Balance", "API".

**Blocked by:** 02

**Status:** done

- [x] Pure balance function per corner/phase (understeer index in degrees, traction, lock-ups per wheel with distance and corner)
- [x] Session view: median over clean laps; available=false with a reason when channels are missing
- [x] /corners rows carry balance; GET /api/sessions/{id}/balance returns per-corner/phase medians + summary
- [x] Corners tab: phase × corner balance heat strip, summary line, lock-up list
- [x] Synthetic sign tests; Austria Q1 vs Q2 (diff on-throttle 55 → 80 %) exit-phase check — if the metric does not move, it is hidden and the finding is written into this ticket
- [x] vitest for colour/summary helpers; headless Chrome check

## Comments

- Done 2026-10-15. Code: `telemetry/corner_balance.py` (pure), `/corners` rows carry `balance`, new `GET /api/sessions/{id}/balance`, `BalanceStrip` in the Corners tab (lap / session-median toggle).
- **Austria diff check (library ids; Spielberg corners, median over each session's clean laps).** Q1 (id 22, `Austria_Q1_wet`) has `diff_onThrottle_setup` 0.55; practice (21), Q2 (23), Q3 (24) and race (25) have 0.80. Q1 was a WET session (78 s laps vs 65-66 s), so the comparison is confounded with grip. Median rear slip ratio on exit (traction, slow / medium / fast corners): Q1 0.171 / 0.092 / 0.074; Q2 0.053 / 0.034 / 0.027; Q3 0.082 / 0.039 / 0.029; practice 0.071 / 0.041 / 0.027; race 0.081 / 0.040 / 0.028. The exit traction metric moves clearly (about 2x in slow corners, 2-3x in the others, far outside the 0.03-0.08 spread of the four 0.80 sessions), so it stays visible. Exit understeer index (slow corners): Q1 -1.28, Q2 -0.16, Q3 -1.81, practice -0.54, race -0.61: too noisy to separate the setups on its own; traction is the discriminating exit metric. Caveat: the Q1 gap is the open diff plus wet track; the test (`test_real_wet_q1_with_the_open_diff_...`) only asserts Q1 traction > 1.3x Q2/Q3.
- **Sign / distribution.** The raw understeer index (front minus rear |slip angle|) is positive in almost every corner because the front tyres carry the steering angle. Library-wide medians over clean laps of all full-export sessions (index in degrees, p25 / median / p75): entry slow 0.98 / 1.41 / 2.09, medium 1.83 / 2.34 / 3.08, fast 1.85 / 2.16 / 2.71; mid slow 1.62 / 2.91 / 3.98, medium 1.92 / 2.79 / 3.56, fast 2.40 / 3.13 / 4.92; exit slow -0.42 / -0.02 / 0.23, medium 0.10 / 0.30 / 0.89, fast 0.43 / 1.40 / 2.35. Calling that "understeer everywhere" would be wrong, so the labels and colours are relative to the typical value per phase (`NEUTRAL_DEG` = entry 2.0, mid 3.0, exit 0.2; slight at +-0.75, strong at +-2.0 degrees); the API returns raw degrees plus `balance_baseline`.
- Deviations: the exit window used for balance and traction runs 40 m past the corner end (`EXIT_EXTRA_M`, capped at the next corner start) because the detected corner ends where full throttle returns, which left the `corner_phases` exit window empty (0-3 m) in most corners. Corner row values are `null` where fewer than 4 cornering samples exist. Lock-ups are attributed to a corner when inside its window or up to 60 m before it (braking zone). Lock-up counts in the session view are summed over the clean laps, so the numbers are large (race: 55 over 14 laps, mostly FR).
- Thresholds (named constants): `LAT_G_MIN` 0.5 g, `STEER_MIN` 0.15, `MIN_SAMPLES` 4, `TRACTION_THROTTLE` 0.5, `LOCK_SLIP_RATIO` -0.15, `LOCK_BRAKE` 0.2, `MIN_LOCK_SAMPLES` 2, `SPIN_RATIO` 0.10 (UI flag).
