# Streamlit → React parity (ticket 02, 2026-11-04)

Every section of `gui_app.py` and the `telemetry/*_ui.py` modules, and where it lives in the React app.
**covered** = React has it (maybe in another form); **port** = missing, ticket in brackets; **drop** = replaced, needs the user's OK.

## Navigation modes (sidebar)

| Streamlit | React | Status |
|---|---|---|
| Import CSV (sidebar) | Library → Import CSV | covered |
| Library stats (sessions, tracks, size, saved) | Library stat tiles | covered |
| Browse sessions + delete | Library table + Delete | covered |
| Strategy planner (`render_strategy_planner`) | Planner | covered |
| Garage: typical Quali / Race setup per track and track state + garage tweaker (`render_garage`, `garage_ui.render_garage_tweaker`: tweak values, estimated impact, proposed card, copy into game) | Setups: generated setup, baseline, duel, track profile; **no typical-setup browser and no tweaker** | port [07] |
| Track dossier (`render_dossier`) | — | port [08] |

## Session tabs

| Streamlit tab / section | React | Status |
|---|---|---|
| Session: pace chart, fuel/tyre stint chart | — | port [03] |
| Session: storage line (CSV → library size) | Session → Details panel | covered |
| Session: tags (type, notes, setup fingerprint) | Session → Details panel (`TagsEditor`) | covered |
| Session: track state as a select (dry / damp / wet …) + condition notes + weather banner | Details: free-text "Conditions" | port [03] (state select + banner) |
| Session: lap table (class, time, Δbest, vmax, full throttle %, coast %, fuel, wear, compound, lock-ups) | Laps tab → "Laps" table | covered (check columns in [03]) |
| Race map: map + driver trace with pinned cursor | Laps tab: TrackMap + Driver trace + cursor | covered |
| Corners: corner Δ bars, engineer phase sentences, brake points vs reference, corner table | Corners tab: "Where and why do I lose time?", callouts, brake-at column, balance | covered |
| Lap compare: map vs ref, sector bar, mini-sectors, trace | Laps tab: sector + mini-sector deltas, trace vs reference | covered |
| vs Session: overlay vs another session (PB default), corner times, engineer panel | ReferencePicker "session" mode (Laps + Corners tabs) | covered (PB default: check in [09]) |
| Single lap: map + trace | Laps tab | covered |
| Single lap: **G-G diagram** | — | port [04] |
| Tyres: car grid, lap trace, stint charts + table, pressures & operating window, allocation editor, compound model | Tyres tab (CarGrid, stints, trends, pressures) + allocation / targets API | covered |
| Strategy: params form, compound specs editor, ranked plans, race trace, review | Strategy tab / StrategyView | covered |
| ERS / 2026: SOC KPIs, ERS trace, deploy vs harvest profile, session scatter, advice map, ERS per corner, practice ERS table, ERS coach, fuel used / DRS / SOC empty, 2026 channels panel | — | port [06] |
| Setup / Stint: follow-up cards, runs in session, A/B vs earlier session, setup evolution + measured experiments | — | port [07] |
| Setup / Stint: setup builder (base: session / best verified / typical) + builder findings + journal save + tweaker | Setups generator / engineer / duel cover "a setup from scratch" but not "build from this practice" | port [07] |
| Setup / Stint: tyre & fuel saving (stint table, efficiency chart, saving insights), fuel & tyre windows (`render_stint_windows_panel`) | — | port [07] |
| Coach: diagnosis headline, top callouts, more callouts (incl. setup follow-ups) | — | port [05] |

## Track dossier (ticket 08)

Track select (raced + catalogue), in catalogue / logged / map learned; track atlas (all circuits, length,
named segments, map learned, your sessions) + corner list preview; open Garage; session-type filter;
learned racing line map; PB, session count, consistency σ, recent spread; lap-time goal (set + gap);
PB history chart, session bests chart; visit history table; setup evolution + latest change;
cross-session overlay (focus picker); corner dossier (latest best vs lifetime PB, worst 3).

## Library upkeep (not UI, but only Streamlit runs it)

`library_maintenance()` in `gui_app.py` runs on every Streamlit start: `reread_library_setups` (server does it
too), `scrub_improbable_lap_records`, `backfill_progress_from_library`, `backfill_setup_fingerprints`,
`backfill_session_tags`, `setup_log.evaluate_all`. New imports already do the per-session part
(`import_session.py`: fingerprint, tags, progress, `evaluate_track`). → ticket 10 moves the idempotent
library-wide upkeep into the server start (after the migrations), so nothing depends on Streamlit.

## Python logic that must survive phase C

Pure helpers inside the UI modules that the ports need, to move into domain modules first:
`tyres_ui.wear_limit` (used by `strategy_ui`), `setup_journal_ui.setup_diff_frame` / `experiments_frame`,
`garage_ui.impact_frame_display` / `setup_copy_frame`, the ERS logic called from `gui_app` (`telemetry/ers.py`,
already pure), `corner_engineer.render_corner_engineer_panel` (Streamlit, delete; `corner_engineer_callouts` stays).
