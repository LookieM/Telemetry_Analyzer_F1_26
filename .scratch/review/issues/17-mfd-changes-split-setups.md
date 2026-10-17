# 17: MFD brake bias / differential changes count as a new setup

**Status:** needs-triage
**Area:** setup identity (runs, offline duel, setup log, baseline) · severity medium

Found in the wheel test 2026-10-17 (Miami FP1, live duel): changing brake bias or on-throttle diff on the MFD
while driving changes `brake_bias_setup` / `diff_onThrottle_setup` in the car-setups packet, so the setup's
mechanical fingerprint changes and the next lap was assigned to contestant B.

- [x] Live duel: `MFD_KEYS` left out of the contestant fingerprint; garage values kept, one feed line on a change
      (`telemetria_server/live/duel.py`).
- [ ] Offline: `telemetry/runs.py::split_runs` starts a new run when `mech_fingerprint` changes, so an MFD change
      mid-stint splits the run (offline duel library groups runs by `mech_fp`, setup log experiments, track baseline).
      Changing `mech_fingerprint` itself would orphan stored fingerprints (duel names in `duel_store`, baselines) —
      needs a decision: separate identity fingerprint for "same setup?" vs. migrate stored ones.
- [ ] Engineer: brake bias / on-throttle diff are A/B parameters but can be moved on the MFD; decide whether to test
      them as "MFD tests" (no garage visit) or keep them as garage parameters.
- [ ] Is engine braking (`brake_engine_setup`) MFD-adjustable in F1 26? If yes, add it to the MFD keys.
