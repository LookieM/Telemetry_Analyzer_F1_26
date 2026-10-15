# 02: Corners detected from the data and a Corners tab with time per corner

**What to build:** corners are detected from a reference lap of the track and stored per track (named from the catalogue by nearest apex, complexes merged, slow/medium/fast class, rebuildable). A new Corners tab in the session page shows one row per corner with time in corner vs a reference (deltas sum to the lap delta), entry / min / exit speed, brake point, trail-brake, full-throttle point and their differences, rule-based callouts above noise; clicking a corner zooms map and traces to it with brake / throttle markers. See spec: Solution 2–3, Implementation Decisions "Corner detection", "Per-track corner storage", "Corner analysis", "API", "React Corners tab".

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Pure corner detection on a lap frame (+ optional catalogue names); unknown tracks get T1..Tn
- [ ] track_corners table, built lazily from the track's best clean lap; rebuild endpoint
- [ ] Pure corner report: per-corner metrics vs reference; corner deltas sum to lap delta within 0.02 s
- [ ] GET /api/sessions/{id}/corners (lap, ref_lap, ref_session) with shape tests and 404/422 paths
- [ ] Corners tab (between Laps and Tyres): reference picker, sortable table with losses coloured, click-to-zoom map + trace with markers, not-enough-data messages
- [ ] Plausibility tests on real sessions (skip when absent): brake point inside corner, vmin ≤ entry/exit, stable corner count between two clean laps
- [ ] vitest for pure helpers; headless Chrome check on a sandbox library copy
