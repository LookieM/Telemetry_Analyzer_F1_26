# 07: Offline duel corrects fuel with 0.03 s/kg, the live engineer and duel with the measured 0.10 s/kg

**Status:** ready-for-agent
**Area:** practice / setups (priority) · bug · severity high

**What happens:** two fuel-effect constants live side by side:
- `telemetry/metrics.py:25` `FUEL_S_PER_KG = 0.030` — used by the offline duel on the Setups page (`telemetria_server/duel_library.py:23, 136, 295, 315`) and as the fallback for the live engineer / duel (`live/engineer.py:209`, `live/duel.py:116`, `live/engine.py:510`)
- `tyres.library_race_stats(root).fuel_s_per_kg` ≈ 0.102 s/kg, measured from 5 same-compound stint pairs — used by the live engine (`engine.py:514`) and the planner

The offline duel compares setups across sessions, i.e. across very different fuel loads (quali 5 kg vs race 35 kg runs). At 0.03 instead of 0.10 s/kg, a 15 kg difference leaves ~1.0 s of fuel effect in the ranking — larger than most setup differences.

**Fix:**
- [ ] one source: the measured library value with 0.10 as fallback, passed into `correct_groups` everywhere (offline duel, live duel, engineer)
- [ ] the duel and engineer result show the value used (already in `correction.fuel_s_per_kg`)
- [ ] remove or rename `metrics.FUEL_S_PER_KG` so the 0.03 cannot be picked up again
- [ ] test: the same laps give the same corrected times offline and live

## Comments
