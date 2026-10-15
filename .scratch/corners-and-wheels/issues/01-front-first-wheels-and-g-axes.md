# 01: Front-first wheels and correct g-force axes, library repaired once

**What to build:** every per-wheel value from an export (tyre temps, pressures, wear, brake temps, slip, lock-ups) is labelled with the wheel it belongs to (exports are FL, FR, RL, RR), the hot-pressure targets pick the right axle, and lateral / longitudinal / vertical g come from the right export axes. The Tyres tab (limiting wheel, front/rear temps, pressures panel) and the React wheel constant follow. Existing library sessions are repaired once at server start after a backup; compact imports without the lateral axis report it as missing. See spec: Solution 1, Implementation Decisions "Wheel order", "G-force axes", "Library repair".

**Blocked by:** None (can start immediately)

**Status:** done

- [ ] One front-first wheel constant in the channel registry; loader labels, car layout indices, lock-up axle split, tyre targets' axle choice, insights/plots label lists derive from it; live UDP order untouched
- [ ] Loader: g_lat = gforce_Y, g_long = −gforce_X, g_mag planar, vertical alias gforce_Z
- [ ] One-off library repair (flag in library_meta, backup of DB + touched parquets, atomic rewrite, idempotent): recompute g from raw gforce_*, compact imports get g_long = −old g_lat and missing g_lat/g_mag, lockup_front/rear swapped
- [ ] Repair runs at server start like the setup re-read; returns a report
- [ ] React wheel constant front-first; per-wheel trace labels correct; car layout unchanged on screen
- [ ] Tests at seam 1 (synthetic rows + tmp copy of real sessions, idempotency, backup); existing suites green
