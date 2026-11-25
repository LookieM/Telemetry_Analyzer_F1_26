# 01: Tyre-set inventory store + live capture

**Status:** done (2026-11-08)
**Spec:** `../spec.md`

- New module `telemetry/tyre_inventory.py`: table `tyre_inventory` (track PK, sets_json, source game|manual, session_type, updated_at); `save_inventory`, `get_inventory`, `clear_inventory`, `available_wear(inv, exclude_fitted)` → {code: [wear %, ascending]}.
- Live engine: per-set snapshot from `state.player_tyre_sets` (compound, wear, available, fitted). Hand it to the server loop when it changes (at most every 5 s). The ingest stores it off-thread, like `game_tyres_pending`.
- Tests: store round-trip, available_wear filter / order.

## Comments
