# 03: Pit loss is measured from incident laps (Spa: 85.9 s)

**Status:** ready-for-agent
**Area:** race live + planner (priority) · bug · severity high

**What happens:** after the Spa replay was recorded (session #50), the Strategy tab says "pit loss measured 85.9 s". A real stop at Spa costs ~20-25 s. The window used laps 3-5 = in-lap 2:06.9, pit lap 2:12.8 (stop with front-wing damage, no wing change) and 2:53.9 (crash + safety car for part of the lap), minus 3 × push median. That value is stored for the track and will drive the planner and the live call for every future Spa race: with 86 s per stop, the model never wants a stop (`screens/s50-strategy.png`: 2-stop plans +77 s).

- `telemetry/tyres.py:541-563` (`measure_pit_losses`): rejects windows with an `invalid` lap and separates `sc`, but accepts `slow` laps; no plausibility bound.
- the SC lap was classed `slow`, not `sc`: SC was out for only part of the lap (`safetyCarStatus` max 1 on lap 5) so `SC_LAP_SHARE` was not reached (`telemetry/metrics.py:320`).

**Fix:**
- [ ] skip a window that contains a `slow` lap, or any SC/VSC sample at all (not only a full `sc` lap)
- [ ] plausibility bound: drop a measured loss outside e.g. 0.5×–2× the catalogue / track default (log it)
- [ ] show the individual measured stops on the Strategy tab so an outlier is visible and can be excluded
- [ ] test: the Spa #50 summary gives no green-flag pit-loss sample

## Comments
