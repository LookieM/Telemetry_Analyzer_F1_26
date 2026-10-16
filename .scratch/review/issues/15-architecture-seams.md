# 15: Architecture seams worth fixing while touching these areas

**Status:** needs-triage
**Area:** architecture · severity low (no user-visible bug on its own)

- **Live engine depends on the API layer:** `telemetria_server/live/engine.py` imports `ParamsIn, build_inputs` from `..api.strategy` inside `update_strategy`. Model assembly (allocation → compound model → overrides) belongs in a domain module both the API and the engine call; the API should only parse requests.
- **`live/engine.py` (890 lines) mixes** packet adaptation, timing, tyres, damage advice, rivals, strategy and engineer/duel wiring. The engineer and duel are already pure modules behind a small adapter — strategy and damage advice could follow the same pattern (pure `decide(state) -> call`), which would also make 01 / 02 / 05 testable without packets.
- **One concept, several constants:** fuel effect (07), SC status meaning (01), lap completeness (08) are each decided in more than one place. One owner per concept.
- **API contract is hand-written twice:** `frontend/src/api/types.ts` (883 lines) mirrors the FastAPI payloads by hand; `tsc` cannot catch a drifted field. Option: generate types from the OpenAPI schema (FastAPI already serves it) and fail the build on a diff.
- **`telemetry/` mixes pure domain and UI-era code** — resolved by 14.

## Comments
