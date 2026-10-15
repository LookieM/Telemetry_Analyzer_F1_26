# 04: Lap comparison can add g-forces and per-wheel channels

**What to build:** in the Laps tab I can add lateral / longitudinal g and per-wheel slip angle, slip ratio and tyre temperatures as extra trace panes, for the focus lap and the reference, with correct FL / FR / RL / RR labels. See spec: Solution 4, Implementation Decisions "API" (compare / lap-channel endpoints), "Laps tab".

**Blocked by:** 01

**Status:** done

- [ ] Compare and lap-channel endpoints accept and return the new channels (per-wheel ones wheel-labelled); API tests
- [ ] Laps tab channel picker adds panes; sessions missing a channel show it disabled with a reason
- [ ] vitest for the trace builders; headless Chrome check
- [ ] Laps tab corner bands come from the stored track corners (same as the Corners tab), not the old catalogue spans
