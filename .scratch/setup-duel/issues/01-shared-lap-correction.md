# 01: Shared lap correction (prefactor)

**What to build:** the engineer's fuel / tyre-age lap-time correction, noise estimate and "counted lap" rules live in one small pure module that both the engineer and the coming duel use. No behaviour change. See spec: Implementation Decisions "Prefactor".

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Pure module with the correction, noise and lap-counting rules; engineer imports it
- [ ] Engineer scenario tests and the capture-replay engine test unchanged and green
