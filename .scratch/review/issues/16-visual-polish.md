# 16: Visual polish of the React app (dark only)

**Status:** needs-triage
**Area:** UI · requested by the user 2026-10-16 ("telemetry is fine, but it looks bare")

**Agreed (grilling 2026-10-16):**
- scope: visual polish **plus** light layout order (hierarchy, grouping, key numbers bigger and higher, less wall-of-text) — a bit of redesign where a section is flat, **no full redesign**, no change in what a page does
- direction: pit-wall / MoTeC readability (graphite, tabular numbers, colour only where it means something) with an F1 character (F1-style font, red accent, angled card headers) — chosen from a prototype: the same Corners and Live pages rendered in 2-3 directions as real screenshots with the user's data
- order: Live (1080×1920) → Session (Laps / Corners / Tyres / Strategy) → Setups → Library + Planner
- **dark theme only**: remove the Light/Dark toggle and the light tokens
- fonts bundled locally (works offline)
- 04 (Live layout per session) is done together with the Live page
- implementation per page by Sonnet subagents (medium); screenshots via headless Chrome before / after

## Comments
