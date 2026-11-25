# 07: Brake bias / differential recommendation per corner

**Status:** needs-triage
**Area:** practice → race (MFD use) · new feature · cost medium
**Source:** real F1 (drivers change brake balance and diff on the wheel several times a lap; engineers give per-corner maps)

**Idea:** from lockups, front/rear slip and the corner balance per phase, recommend MFD changes per corner: "T1: BB +1 (front lockups 3/5 laps), T10: on-throttle diff −1 (exit oversteer)". Check later laps for the effect.

**What exists:** lockup detection (`telemetry/balance.py`, `telemetry/corner_balance.py`), per-corner phase balance (Corners tab, `BalanceStrip`), MFD brake bias / on-throttle diff handled in the live duel and engineer (`telemetria_server/live/duel.py`, `engineer.py`; commit 0bab0d6). No per-corner recommendation, no check whether the driver changes BB mid-lap.

**Decisions needed (triage):**
- does the driver actually use BB / diff on the wheel during a lap? If not, this becomes one baseline value per track (setup), not a per-corner map
- recommendation only, or also verify from recorded MFD changes

**Depends on:** review/09 (corner detection).

## Comments
