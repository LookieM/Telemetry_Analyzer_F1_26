# 14: Retire Streamlit — dead modules and what the React app still lacks

**Status:** needs-triage
**Area:** architecture · cleanup

**Dead after retirement** (not reachable from `telemetria_server/` by import graph, 2026-10-16): `telemetry/coach.py`, `ers_2026_ui.py`, `garage_ui.py`, `lap_views.py`, `race_windows.py`, `session_compare.py`, `setup_journal_ui.py`, `stint_coach.py`, `strategy_ui.py`, `tyres_ui.py` + `gui_app.py` (1815 lines). `corner_engineer.py` is reachable from the server but still has an optional `import streamlit` (line 234). `plots.py` (1137 lines, Plotly) is reached only through Streamlit-era helpers — check before deleting.

**In Streamlit, not in React** (decide per item: port, replace, or drop):
- ERS / 2026 tab (practice ERS table, ERS coach)
- Coach feed + insights (top callouts, ranked feed)
- Track dossier: visit history, setup evolution, cross-session overlay, corner dossier vs lifetime PB
- Setup builder + setup journal (partly replaced by generator / engineer / duel)
- Tyre & fuel saving section (Setup / Stint tab)
- "vs Session" cross-session lap compare (React has "Another session" reference — check parity)

**Also an engineering gap:** no live strategy in the wet (`engine.py`: weather ≥ 3 → "Wet running: no live dry-strategy call"); no inter/wet crossover call.

## Comments
