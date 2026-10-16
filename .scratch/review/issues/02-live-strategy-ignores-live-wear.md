# 02: Live strategy ignores the wear and pace of the current stint

**Status:** needs-triage
**Area:** race live (priority) · engineering gap · severity high

**What happens:** the BOX/STAY call and the box window come only from the library compound model (`tyres.track_compound_model`) plus live fuel burn. The tyre wear the game reports every lap, and the stint's real lap-time trend, never reach the decision. When the race runs hotter or cooler than the library, the window is wrong.

**Evidence:** Spa replay, C4 start, model window "lap 3–8". Measured front-right wear 10 % → 18 % → 28 % → 41 % on laps 1-3 (≈ 10-13 %/lap); at the 69 % limit that is a stop around lap 5, but the card said STAY with window 3-8 (`screens/live-spa-lap4.png`). Memory note from phase 4 already listed "live deg correction from current-stint laps (not blended yet)".

- `telemetria_server/live/engine.py:838-880` (`update_strategy`): inputs = `build_inputs(root, track, "dry", ParamsIn(laps, fuel_per_lap))`; `age` from `m_tyresAgeLaps` is the only stint input.

**Decisions needed (triage):**
- how to blend: replace the model's wear %/lap for the current compound by the measured stint rate after N laps (with a floor of the model), or a weighted blend
- same for degradation s/lap (noisier — traffic, ERS, fuel already corrected)
- show on the card which numbers are measured live vs from the model ("wear 11.2 %/lap live · model 7.0")

## Comments
