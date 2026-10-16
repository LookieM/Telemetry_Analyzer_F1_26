# 01: Formation lap triggers "BOX under SC"

**Status:** ready-for-agent
**Area:** race live (priority) · bug · severity high

**What happens:** during the formation lap the Live page shows a full red **BOX — under SC** card and the event strip logs "Strategy: BOX for C3 (M)". The game reports `m_safetyCarStatus = 3` (formation lap); the strategy treats every non-zero status as a safety car.

**Evidence:** `screens/live-formation-box.png` (Spa replay, `data/udp_captures/20261009-222554.f1cap`, first 90 s).

- `telemetria_server/live/engine.py:875-876` — `call = plan["call_sc"] if sc_now else plan["call_green"]` (3 counts as SC)
- `frontend/src/pages/Live.tsx:148` — `const under = session.sc > 0`
- The damage path already does it right: `engine.py:780` uses `in (1, 2)`.

**Fix:**
- [ ] SC / VSC = status 1 / 2 only, in the engine and the UI (one helper, not three comparisons)
- [ ] no strategy call before the race lap 1 has started (formation / grid): show "Strategy call starts after the first lap"
- [ ] formation shown as its own flag, not as "SC"
- [ ] test: a snapshot with status 3 never produces `call == "BOX"` from the SC branch

## Comments
