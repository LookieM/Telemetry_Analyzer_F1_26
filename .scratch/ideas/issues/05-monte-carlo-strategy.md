# 05: Monte Carlo strategy — outcome distribution instead of one best plan

**Status:** needs-triage
**Area:** race planning (Planner) + race live · new feature · cost high
**Source:** real F1 (Monte Carlo with random SC, traffic, overtaking difficulty — Pirelli, Aston Martin, Red Bull); open race simulators (arXiv)

**Idea:** simulate the race N times with random SC / VSC (per-track probability and timing), traffic after stops and pace noise; rank plans by expected time AND risk ("plan A: best median, 30 % chance to lose 10 s if no SC; plan B: robust"). Live: re-run on the current state to answer "what if a SC comes in the next 5 laps".

**What exists:** `telemetry/strategy.py` deterministic DP: `optimise`, `shortlist`, `sensitivity`, `race_calls`, with a single `sc_pit_factor` (0.55). The Planner shows ranked plans + sensitivity. No SC probability, no traffic, no randomness.

**Decisions needed (triage):**
- SC probability source: library history per track (few races) vs a fixed seed per track
- with AI-only races, does a distribution change the decision often enough? (prototype on 2–3 past races first)
- runtime budget live (worker thread, number of sims)

**Depends on:** 04 (traffic needs rival pace), review/03, review/05, review/07.

## Comments
