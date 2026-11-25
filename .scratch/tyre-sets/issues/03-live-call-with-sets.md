# 03: Live strategy fits only the sets you still have

**Status:** done (2026-11-08)
**Spec:** `../spec.md` · **Blocked by:** 02

- `plan_from_state(..., inventory)`: the cost-to-go and `fit_compound` use the available sets minus the fitted one, freshest first. The result carries `fit_wear`. `fit_label` reads e.g. "M (used 23%)".
- Engine `update_strategy` passes the live inventory (no TyreSets packet → old behaviour).
- Test: with no M set left the fit is not M.

## Comments
