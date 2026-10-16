# 12: Small UI / data issues found in the review

**Status:** ready-for-agent
**Area:** various · severity low

- [ ] Live idle text hard-codes "port 20777" (`/live` waiting screen) even when the server listens on another `--udp-port`; take it from `/api/live/status`.
- [ ] Recorded-session import log says "0.0 MB -> 8.5 MB (saved -8.5 MB)" for live sessions (no source file); say "recorded, 8.5 MB".
- [ ] Tyres tab: "LAPS TO 69 %" in the header row reads as "laps left on this set" but is the margin at the stint's end (Monaco #16 focus lap 15, age 1: "1.9") — label it per stint or compute from the focus lap.
- [ ] Tyres tab on compact imports compares **surface** temperature with the 80-100 °C window (meant for inner/carcass): fronts always "cold, in window 3 %" (`screens/s16-tyres.png`). Hide the window when only surface temp exists.
- [ ] Corners tab: "Corners detected from session #4's lap 8" — say which session (track · type · date) and offer the rebuild from this session.
- [ ] Live under SC: delta vs session best (+53.96) is meaningless behind the SC; the export has `safetyCarDelta` — show the SC delta instead while SC/VSC is out.
- [ ] Live: SC lap that is only partly behind the SC is classed `slow` (see 03) — check the class shown in lap pickers ("Lap 5 — 2:53.912 (slow)").

## Comments
