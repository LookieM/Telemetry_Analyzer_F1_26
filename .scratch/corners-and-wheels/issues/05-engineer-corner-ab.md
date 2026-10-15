# 05: The live engineer compares the two variants corner by corner and phase by phase

**What to build:** for each counted lap of an engineer pair, the live engine turns the recorder's distance-binned lap frame into a corner profile (per corner: time, per-phase time, understeer index, rear slip on exit) using the track's stored corners (built from a live lap if none); the engineer averages the profiles per variant and adds the top corner/phase time and balance differences and a check of my tags against them to its result; the Engineer card shows them under the stopwatch line; the stored test record keeps them; missing profiles fall back to sectors. See spec: Solution 5, Implementation Decisions "Engineer corner/phase A/B".

**Blocked by:** 02, 03

**Status:** ready-for-agent

- [ ] Pure lap → corner profile function (reuses 02/03 analysis)
- [ ] Ingest hands completed lap frames to the engine; EngineerLap carries the optional profile
- [ ] Engineer result: corners (top 5 by |delta|) and tag_check; history + persisted record include them; sector fallback
- [ ] Scenario tests at the engineer seam; capture-replay engine test still green
- [ ] Engineer card shows the corner rows and tag check; vitest for helpers; headless Chrome check at 1080×1920
