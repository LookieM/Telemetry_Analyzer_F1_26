# 02: Optimiser respects set count and used-set wear

**Status:** done (2026-11-08)
**Spec:** `../spec.md` · **Blocked by:** 01

- `strategy._Costs(specs, params, inventory)`: per compound, the k-th freshest set has its own cost curve (start age = wear / wear rate) and its own max laps. Without an inventory: the old fresh, unlimited behaviour.
- `optimise`: a compound appears at most as many times as you have sets of it. The plan records each stint's set (slot index, start wear). `describe` shows the wear of a used set.
- `_windows`, `lap_times`, `sensitivity`, `race_calls` (cost-to-go over state = compounds used + sets consumed) take the same sets.
- API `/strategy/optimise`: `use_inventory` (default true). The payload carries `inventory` and per-plan `start_wear`. GET/PUT/DELETE `/tracks/{track}/tyre-sets`.
- Tests: count limit, used set slower and shorter, worn-out set excluded, no inventory = unchanged, DP vs brute force with sets.

## Comments
