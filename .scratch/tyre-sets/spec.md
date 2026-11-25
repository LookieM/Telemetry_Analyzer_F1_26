# Tyre sets in the strategy (count + wear)

From idea `ideas/issues/11-tyre-set-inventory.md` (driver, 2026-11-08). The driver asked to build it right away ("dawaj i tickety oraz kompilację"), so the open triage questions were settled with these defaults. Each one can be changed later.

## Decisions (defaults taken without a grilling)

- **Which snapshot:** the latest TyreSets state seen for the track, whatever the session was. It is saved whenever it changes (throttled). After Q the planner sees what Q left you. The session type and time are shown next to it.
- **Which sets count:** `m_available == 1`, every compound (slick, inter, wet). Pre-race the fitted set counts too. Live, the fitted set is the current stint and is left out of what remains.
- **Manual edit:** a "my sets" table in the Planner, saved as source `manual`. The next game snapshot replaces it (game data is fresher). "Clear" goes back to no limit.
- **Switch:** "Plan with my sets" in the Planner, on by default when an inventory exists. Without an inventory: the old model (unlimited new sets), and the UI says so.
- **Used set model:** equivalent start age = set wear % / compound wear %/lap. Laps left = (wear limit − set wear) / wear rate. A set at or past the limit is unusable. A compound with no wear rate counts its sets but ignores wear.
- **Choice of set:** for a compound used n times, take the n freshest sets. A fresher set dominates (deg ≥ 0) and stint order does not change the cost, so no permutation search is needed.
- **Start tyre:** free choice. Not locked to the fitted set.
- **Race review:** unchanged (unlimited fresh). The review compares against the model optimum.

## Tickets

- 01 inventory store + live capture
- 02 optimiser with set limits and used sets (planner, sensitivity, pit-wall calls)
- 03 live call fits only sets you have
- 04 Planner UI: my sets panel, plan labels with wear
