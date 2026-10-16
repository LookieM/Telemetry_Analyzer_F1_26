# 06: Engineer test always drives variant 1 then 2 — session drift is not cancelled

**Status:** needs-triage
**Area:** practice engineer (priority) · method · severity medium

**What happens:** each pair is run A then B (`telemetria_server/live/engineer.py:442-445`: variant "1" until its target, then "2"). Laps are corrected for fuel and tyre age, but not for track evolution and the driver getting faster during the session, which in the library is often several tenths (Baku FP1 #49: 1:45-1:46 early, 1:43-1:44 later). The baseline is randomly 1 or 2, so the bias is not systematically for the change, but it lands in the verdict as an unmodelled error the noise estimate does not contain.

Related: with 3 laps per variant and a lap-to-lap spread of 0.3-0.5 s, the smallest measurable difference is ~0.3-0.4 s; most single-parameter steps (wing ±3, ARB ±3) are smaller. The test then rests on feel — fine by design (optometrist), but the driver is not told this before investing 18-50 minutes.

**Decisions needed (triage):**
- ABA (1 → 2 → 1, two short runs of 1) or ABBA order, at the cost of one more garage visit — or a drift term estimated from the reference laps
- show the expected minimum detectable difference at start ("with your spread, the stopwatch decides differences above ~0.35 s")

## Comments
