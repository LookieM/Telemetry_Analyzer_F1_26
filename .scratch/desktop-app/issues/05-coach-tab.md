# 05: Coach tab: diagnosis headline, top callouts, insights (B3)

**Status:** done
**Area:** Streamlit retirement (review/14)
**Blocked by:** 02

Spec: `../spec.md` phase B/C. Port pattern: pure logic → `telemetry/` domain module, endpoint in `telemetria_server/api/`, types + hook in `frontend/src/api/`, UI from existing components, pytest + vitest + e2e.

## Comments
- 2026-11-04: done: `telemetria_server/api/coach.py` (`GET /sessions/{id}/coach`: `coach_feed_for_session` + setup follow-ups), registered in `app.py`; `pages/CoachTab.tsx` + `.css`, `lib/coach.ts` + test, hook `useCoach`, types `CoachPayload`. Tests: `tests/server/test_coach_api.py`, e2e "coach: session read…". To run: pytest, tsc, vitest, e2e; check the response time on a long race (loads all columns).
- Verified: pytest (coach, library, desktop), vitest 133/133, e2e 10/10, headless screenshots. Coach takes 2.4-4 s on a 30-lap race.
