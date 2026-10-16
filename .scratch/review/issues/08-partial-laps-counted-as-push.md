# 08: Incomplete laps are counted as push laps (fake best laps, fake deltas)

**Status:** ready-for-agent
**Area:** all analysis (priority: feeds practice + race) · bug · severity high

**What happens:** a lap counts when it covers ≥ 72 % of the track (`telemetry/metrics.py:18` `MIN_LAP_DISTANCE_FRAC = 0.72`). Its lap time is then the timer at the last sample — not a lap time.

**Evidence:**
- Miami Race #47: "best lap" ★ **lap 4 — 1:30.732** ends at 5124 m of 5410 m (export cut). It is the session's best, the default focus lap, the Corners reference and the "biggest loss" basis (`screens/s47-corners.png`: Δt falls to −100 s and the speed trace to 0 at the end).
- Baku FP1 #49: lap 11 — "1:44.004", class `push`, 4839 m of 5994 m. Choosing it as reference shows **−13.464 s** although the lap times differ by 0.97 s (`screens/s49-corners.png`).

Downstream: best lap / PB, references, tyre degradation fits, pit-loss windows (03), track profile and corner detection (if the partial lap is the reference), duel and engineer library runs.

**Fix:**
- [ ] a lap is complete only when it reaches the line: coverage ≥ ~97 % of the track length (or the next lap starts); otherwise class `partial`, never `push`
- [ ] `partial` shown in lap pickers like `in` / `out`, excluded from best lap, references, fits
- [ ] re-classify stored sessions on startup (laps table only; no parquet rewrite)
- [ ] tests: #47 lap 4 and #49 lap 11 become `partial`; Miami race best becomes lap 1 (1:32.516)

## Comments
- 2026-10-16 (real game, pad, Miami FP1 #52, 14 laps): every lap with a **garage visit** (laps 4, 8, 11 — garage values change mid-lap, tyre age resets, 7-9 game-minutes in the garage) is one merged lap: the partial lap before the garage + the out-lap from the pit exit, class `push`. `pit_status` stays 0 in the garage and the recorded frames carry no `driverStatus`, so nothing marks them. Lap 11 "1:32.601" — the session best — is such an out-lap timed from the pit exit. Fix scope grows: the recorder must keep `driverStatus` (garage / out-lap / in-lap), and the classifier must mark a lap whose garage values or tyre set change mid-lap as `out` (or split it).
- 2026-10-16: the driver confirmed the garage visits were the menu's **"Return to garage"** (teleport, to save time), not a drive into the pit lane — the normal way they run practice. So: no in-lap, no pit lane, the interrupted lap is abandoned and the lap number does not change. The recorder must treat `driverStatus == 0` (garage) as the end of the current lap (drop the partial), and the lap after it as an out-lap; the engineer / duel instructions should say "return to the garage (menu is fine)" instead of "box".
