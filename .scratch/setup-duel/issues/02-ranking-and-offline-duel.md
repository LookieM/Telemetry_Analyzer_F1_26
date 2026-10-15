# 02: Ranking and the offline duel on a per-track Setups page

**What to build:** a new Setups page per track lists the distinct setups I have driven there (mechanical fingerprint, name, runs). I pick 2–3 and get a ranking: 70 % race pace (fuel/tyre-corrected, plus wear cost over a 50 % race via the strategy model) + 30 % one-lap pace, noise band, balance per phase (step 3) and the tie-break used — or "not comparable because…". I can name a setup. See spec: Solution "Offline", "Ranking"; Implementation Decisions "Ranking", "Offline duel", "Storage" (setup_names, duels), "React".

**Blocked by:** 01 (and corners-and-wheels 03 for the balance column)

**Status:** ready-for-agent

- [ ] Pure ranking function (weights, noise band, tie-breaks stopwatch → balance → feel, wear cost with fallback)
- [ ] Candidates from the run splitter across the track's sessions, comparability filter with reasons
- [ ] GET /api/tracks/{track}/setups, POST /api/tracks/{track}/duel, PUT /api/setups/{fingerprint}/name; duels stored
- [ ] Setups page (route + links from library and session page): candidates, naming, picker, result table
- [ ] Tests: ranking on synthetic + real library runs; API on tmp library; vitest helpers; headless Chrome
