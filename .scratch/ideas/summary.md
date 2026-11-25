# Feature ideas — 2026-10-27

From a comparison with other F1 / sim-racing telemetry tools (SRT, RaceLab, SimRacingSetup, Pitbox, Track Titan, Coach Dave Delta, F1Laps, Garage 61) and with how real F1 engineers work. All tickets are **needs-triage**; none is specified enough for an agent yet. Fix the data first: review/13 (wheel test), then review 01 → 08 → 03 → 07 — most ideas below read push laps, pit loss or corners.

Not taken over (decided in the comparison): cloud / community / setup shop (offline, solo), voice radio (text feed only), in-game overlays (SimHub covers them).

| # | Idea | Source | Cost | Depends on |
|---|---|---|---|---|
| 01 | Ideal lap from best mini-sectors + inconsistency | real F1 | low | review/08 |
| 02 | "Biggest mistake first" — one ranked fix per lap | Track Titan, Delta | medium | review/08, 09, 14 |
| 03 | Racing line vs a reference lap (+ per-track reference) | Delta, GO Fast | medium | — |
| 04 | Rival model, predicted stops, undercut / overcut | real F1 | medium-high | review/03, 05 |
| 05 | Monte Carlo strategy (SC, traffic, risk) | real F1 | high | 04, review/03, 05, 07 |
| 06 | Energy 2026: harvest/deploy map, clipping, lift & coast | real F1 2026 | medium-high | (phase 5.3) |
| 07 | Brake bias / diff per corner | real F1 | medium | review/09 |
| 08 | Wet strategy + crossover call | real F1, SRS forecast | medium | — |
| 09 | Practice run plan + event log | real F1 | medium | review/13 |
| 10 | Automatic race debrief | real F1 | medium | review/03, 08 (phase 5.3) |
| 11 | Strategy knows your tyre sets (count + wear) | driver 2026-11-08 | medium | — (pairs with review/02) |

Suggested best value for cost: 01, 04, 06.
