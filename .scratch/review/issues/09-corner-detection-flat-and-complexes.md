# 09: Corner detection skips flat corners, merges complexes and names corners wrongly

**Status:** needs-triage
**Area:** corners → track profile → setup generator / engineer A/B · method · severity medium

**What happens:** a corner = a stretch without sustained full throttle (`telemetry/corner_detect.py` header). By construction:
- **flat-out corners never exist** (Miami T9-T10, Spa Eau Rouge / Blanchimont, Silverstone Copse / Maggotts). The track profile then reports **fast corners 0 %** at Miami (`screens/setups-miami.png`), and similarity / the setup generator see high-downforce corners as straights.
- **complexes merge**: Miami has 5 corners; "T12–T16" is 674 m with 5 speed minima (`/api/tracks/Miami/corners`: `merged_from` 3161…3602 m). Entry/mid/exit of that "corner" is T12 entry / somewhere / T16 exit, so the engineer's corner-and-phase A/B and the balance strip are coarse exactly where the lap is decided.
- **names off by one**: Baku "C1" (brake 174 m) is real T1 and "T1–T3" (556 m) is T2/T3; Spa "C2" at 2341 m is Les Combes and "Les Combes / Malmedy" at 2663 m is the next one (`screens/s49-corners.png`, `/session/50/corners`). The catalogue apex fractions do not line up with detected corners (memory note from phase 5: "catalog corner windows misaligned").
- Miami corners come from **session #4** (an old compact import) — the source of truth for a track is not the best/latest full export.

**Decisions needed (triage):**
- detect fast corners from lateral g / steering (a flat corner = sustained |g_lat| > ~2.5 g or steering), as their own speed class
- split complexes at each speed minimum for the table and A/B, keep the complex as a group label
- naming: match by order + nearest catalogue apex after aligning the start offset, or drop catalogue names and use C1..Cn
- which session/lap defines a track's corners (best full-channel lap, rebuild when a better one arrives)

## Comments
