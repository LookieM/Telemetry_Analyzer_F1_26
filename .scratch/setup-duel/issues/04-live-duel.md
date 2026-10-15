# 04: Live duel in the Engineer card

**What to build:** in practice I start a Duel (2 or 3 contestants, optional names) from the Engineer card. The app recognises each setup from the game's setup packet when I leave the garage (A, B, C in order; warns on repeats / pressure-only differences), counts 3–5 clean laps each with fuel/tyre correction and tyre-set hints, asks me to rank by feel when done, shows its ranking (same function as offline) and I confirm the winner, which becomes the track baseline. Only one live program at a time. See spec: Solution "Live"; Implementation Decisions "Duel module", "One live program at a time", "React".

**Blocked by:** 01, 02, 03

**Status:** ready-for-agent

- [ ] Pure duel module with view()/result() and commands; practice + dry only
- [ ] Engine routes to the active program; /api/live/duel/* endpoints; 409 when the other program runs; snapshot key `duel`
- [ ] Winner stored as duel + baseline
- [ ] Engineer card: duel start, run panel, feel ranking form, ranking table
- [ ] Scenario tests, API tests, capture-replay test green; vitest; headless Chrome at 1080×1920
