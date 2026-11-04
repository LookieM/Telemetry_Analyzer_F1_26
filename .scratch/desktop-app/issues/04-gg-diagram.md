# 04: Single lap G-G diagram in the Laps tab (B2)

**Status:** done
**Area:** Streamlit retirement (review/14)
**Blocked by:** 02

Spec: `../spec.md` phase B/C. Port pattern: pure logic → `telemetry/` domain module, endpoint in `telemetria_server/api/`, types + hook in `frontend/src/api/`, UI from existing components, pytest + vitest + e2e.

## Comments
- 2026-11-04: done: `components/GGDiagram.tsx` (SVG, speed colour, 0.5 g rings, follows the lap cursor), `lib/gg.ts` + `gg.test.ts` (passed), panel "G-G · lap N" in the Laps tab via lap extras `g_lat` / `g_long`. To run: tsc, e2e ("laps: session pace chart and the G-G diagram…").
- Verified: pytest (coach, library, desktop), vitest 133/133, e2e 10/10, headless screenshots. Coach takes 2.4-4 s on a 30-lap race.
