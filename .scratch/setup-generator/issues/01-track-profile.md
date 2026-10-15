# 01: Track profile

**What to build:** each track has a profile — shares of lap distance in slow / medium / fast corners and at full throttle, heavy braking zones, length — from its stored corners when I've driven it, else estimated from the catalogue and labelled so; shown on the Setups page; similarity between tracks (reverse layouts share with a penalty). See spec: Implementation Decisions "Track profile".

**Blocked by:** corners-and-wheels 02, setup-duel 03

**Status:** ready-for-agent

- [ ] Pure profile from stored corners and from the catalogue (all 28 layouts); similarity function
- [ ] Profile in the Setups page payload and UI
- [ ] Tests: real library tracks (fractions sum, Monza vs Monaco/Hungaroring full-throttle), all catalogue layouts
