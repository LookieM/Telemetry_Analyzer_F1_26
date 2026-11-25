# 11: Strategy knows the tyre sets you actually have (count + wear)

**Status:** ready-for-agent — moved to `.scratch/tyre-sets/` (spec + tickets 01-04), 2026-11-08
**Area:** Planner + race live · strategy model · cost medium
**Source:** driver, 2026-11-08: "w planerze nie bierze pod uwagę tego ile 'nowych' opon i jakich mam w dostępie"

**Problem:** both strategy paths assume every stint starts on a **fresh** set and that there are **unlimited** sets of each compound.
- Planner: `telemetry/strategy.py` `optimise` uses `combinations_with_replacement` over compounds; `_Costs` builds each stint's cost from tyre age 0. It can suggest M → M → S with one M set left, or none.
- Live: `plan_from_state` (`strategy.py`) picks `fit_compound` from every compound in the model, ignoring whether a set is left and how worn it is.

**What exists:** the game's TyreSets packet (id 12, `telemetria_server/udp/structs.py` `TyreSetData_DT`) gives, per set (20): actual/visual compound, `m_wear` %, `m_available`, `m_useableLife`, `m_lapDeltaTime`, plus `m_fittedIdx`. The live engine holds it (`state.player_tyre_sets`) and already builds a per-set list (`engine._tyre_sets`: compound, available, fitted, wear, life) for the engineer / duel. But what is stored (`engine._collect_game_tyres` → `compounds.save_game_tyres`) is reduced to **one entry per compound** (role, life, delta) for the allocation, **once per session start**. Set count, wear and availability are dropped. SRT exports have no TyreSets data at all.

**Proposed shape:**
1. **Inventory store:** keep the latest per-set snapshot (compound, wear %, available) per track + session (session type, time), refreshed on every TyreSets packet / at session end, so the state after Q is what the race planner sees.
2. **Optimiser:** a compound may appear at most as many times as you have available sets of it. A used set starts its stint at an equivalent age (wear % / wear rate), so it is slower and has fewer laps left before the wear limit. For a compound used n times take the n freshest sets (a fresher set dominates while deg ≥ 0; stint order does not change the cost, so no permutation search). Plan label shows the set: "S (used 38 %) 14 → H new 22".
3. **Live:** `plan_from_state` and `fit_compound` only consider sets still available, with their wear.
4. **Planner UI:** a "my sets" table (from the game with its source + time, editable by hand) for when the app did not run during Q, or there is only an SRT export. Without inventory: today's behaviour (unlimited fresh), stated in the UI.

**Decisions needed (triage):**
- game mode the driver uses (full weekend FP/Q → race vs race only with a fixed allocation): which snapshot is "pre-race" — last Q, or the pre-race grid screen?
- start tyre: fixed to the fitted set at the grid, or free choice in the plan?
- does the review (`review_race`) also need the inventory (a plan "best" you could not have run)?
- equivalent-age model for used sets: wear % / measured wear rate, or the game's `m_lapDeltaTime` for that set?

**Depends on:** nothing hard; pairs with review/02 (live wear in the strategy).

## Comments
