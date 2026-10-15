# 03: Track baseline — stored, shown as garage values, offered by the engineer

**What to build:** a track has one active baseline setup (with history): set from a duel winner, from an engineer test's final setup, or from a library session. The Setups page shows it as garage values in game order and units to type into the game; the engineer offers its final setup as the new baseline when it finishes. See spec: Solution "Track baseline"; Implementation Decisions "Storage" (track_baselines), "Engineer link", "React".

**Blocked by:** 02

**Status:** done

- [ ] track_baselines table, one active per track, history; GET/POST /api/tracks/{track}/baseline
- [ ] Setups page baseline card (garage order/units, source, history, restore older)
- [ ] Engineer view carries baseline_offer at the end; Engineer card accepts it
- [ ] Tests: API on tmp library; engineer scenario for the offer; vitest; headless Chrome
