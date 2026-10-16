# 05: The live call does not know where you rejoin (traffic, undercut, VSC vs SC)

**Status:** needs-triage
**Area:** race live (priority) · missing feature · severity medium

**What happens:** BOX/STAY is pure time: own race time to the flag, nothing about the cars around. A race engineer's first questions at a stop are "where do we come out?" and "does the car behind undercut us?". The engine already has every input (gaps of all cars, pit loss, rival tyre age and stops); only a crude `threat` flag exists (`engine.py:830-833`: car behind within 25 % of a pit loss with older tyres).

Also: SC and VSC use one `sc_pit_factor` (0.55, `strategy.py:589`); under VSC a stop saves noticeably less than under a full SC.

**Decisions needed (triage):**
- rejoin prediction on the strategy card: "box now → rejoin P14, 1.2 s behind STROLL (C2, 1 lap old)"
- separate SC and VSC factors, measured from the library where stops exist (`sc_pit_losses` already exists for SC)
- whether position may change the call itself (e.g. STAY when rejoining in a DRS train) or only inform it

## Comments
