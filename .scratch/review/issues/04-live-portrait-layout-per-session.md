# 04: Live portrait layout does not adapt to the session — rivals cut to one row in a race

**Status:** done
**Area:** race live (priority) · UI · severity high

**What happens:** the Race Engineer card (Short / Full) and the Setup duel form are always rendered (`frontend/src/pages/Live.tsx:372`), also in a race, where neither can be used. On the 1080×1920 screen they take ~450 px, so the rivals table — the main thing to watch in a race — shows **one row** and the event chips are cut at the bottom (`screens/live-formation-box.png`, `screens/live-sc-wing.png`). In practice the opposite happens: the strategy card shows a placeholder "Strategy runs in races only" (`Live.tsx:146`).

**Fix:**
- [ ] race: no engineer / duel card (or a one-line collapsed row); strategy + rivals get the space; rivals show ±5 cars around you
- [ ] practice: no strategy placeholder; engineer / duel card gets the space; long-run block visible
- [ ] quali: delta + tyres + fuel; neither strategy nor engineer
- [ ] check at 1080×1920 with the Spa replay and a practice replay (CDP screenshots)

## Comments
