Status: ready-for-agent

# Starting setup from scratch, with honest confidence (roadmap step 5)

## Problem Statement

For a track where I have no baseline yet (no duel winner, no engineer test) the app has nothing useful to
give me: the old Streamlit "typical setups" are hand-made guesses (e.g. 55 kg race fuel when I run ~22 kg
at 50 % distance), they ignore what I have learned on other tracks, and they never say how much to trust
them. I want a starting setup computed from what the app knows — the track's character and my own results
on similar tracks — clearly marked with how confident it is, so that the engineer's first test goes after
the least certain parameter. Today the library has no engineer tests or duels yet, so at first the
answer will lean on the prior; it must say so and improve as results come in.

## Solution

A **setup generator** produces a full garage setup for a track, per parameter with a value, a source and a
confidence:

- **Track profile:** a small vector describing the track — share of lap distance in slow / medium / fast
  corners and at full throttle, number of heavy braking zones, top-speed proxy — computed from the track's
  stored corners (step 3) when I have driven it, else from the catalogue (corner kinds, length) and marked
  as such.
- **Evidence:** active track baselines (step 4), engineer settled values (step 2) and duel results on other
  tracks, each with the track's profile. The prior is the existing typical-setup table, corrected where it
  is known to be wrong (race fuel from my measured consumption × the 50 % race laps; camber stays meta).
- **Per-parameter estimate:** for each tested parameter (wings, diff on/off, ARBs, springs, ride heights,
  brake bias / pressure, pressures), a similarity-weighted blend of the evidence from similar tracks pulled
  toward the prior, snapped to the garage step and range, with suspension coherence kept. Confidence per
  parameter = how much and how similar the evidence is: "low – prior only", "medium", "high"; overall
  confidence = the weakest of the aero / mechanical groups.
- **Where it shows:** the Setups page (step 4) for any track — the baseline when one exists, otherwise the
  generated setup with confidence badges, the evidence it used ("Front wing 27: from Spielberg baseline
  (similarity 0.82) and Zandvoort settled 25; prior 30") and the suggestion "test front ARB first (lowest
  confidence)". I can make it the track baseline. The engineer's optometrist program, when started on a
  track whose baseline came from the generator, tests the lowest-confidence parameters first.
- **Quali vs race:** one setup (parc fermé) with the race weighting the user agreed (70/30); fuel shown for
  both quali (minimum) and race (consumption × laps + margin).

## User Stories

1. As a driver, I want a full starting setup for a track I've never set up, so that I don't begin from a random internet setup.
2. As a driver, I want each parameter's confidence shown, so that I know what to trust.
3. As a driver, I want to see which tracks and results each value came from, so that I can judge it.
4. As a driver, I want the track's character (slow/medium/fast corners, full-throttle share, heavy braking zones) shown, so that I understand why it resembles other tracks.
5. As a driver, I want the profile from my own driving when available and from the catalogue otherwise, labelled, so that I know its quality.
6. As a driver, I want results from similar tracks to count more than from different ones, so that Monza doesn't shape Monaco.
7. As a driver, I want the old typical-setup table used only as a prior with its known errors fixed (race fuel from my real consumption), so that obvious nonsense is gone.
8. As a driver, I want camber kept at the meta and values snapped to the garage steps and ranges, so that the setup can be entered in the game exactly.
9. As a driver, I want springs and anti-roll bars kept coherent, so that the generator doesn't produce a floppy rear.
10. As a driver, I want an honest "low confidence – prior only" when there is no evidence, so that I'm not misled.
11. As a driver, I want the generated setup to improve automatically when new baselines, duels or engineer tests exist, so that the app learns from me.
12. As a driver, I want a suggestion of which parameter to test first (lowest confidence among the ones that matter most), so that practice time goes where it helps most.
13. As a driver, I want to make the generated setup the track baseline in one click, so that I can start from it.
14. As a driver, I want the engineer to test lowest-confidence parameters first when the baseline came from the generator, so that tuning targets uncertainty.
15. As a driver, I want quali and race fuel shown with the race fuel from my consumption, so that I fill the right amount.
16. As a driver, I want the generator to work for every catalogue track (all 28 layouts), so that no track is left out.

## Implementation Decisions

- **Track profile (pure):** from stored corners: fractions of lap distance in slow / medium / fast corners
  and at full throttle, heavy braking zones (entry speed − vmin > 100 km/h), lap length; from the catalogue:
  same fields estimated from catalogue corner kinds / fractions, marked `source: "catalogue"`. Similarity =
  exp(−distance) over standardised fields; reverse layouts share the forward layout's evidence with a
  small penalty.
- **Evidence collection:** active baselines (step 4), engineer settled values, duel winners — per track,
  per parameter, with recency; nothing from the target track itself except an existing baseline (then the
  generator is not needed and the page shows the baseline).
- **Estimator (pure, deep):** per parameter: weighted mean of evidence values with weights = similarity ×
  source weight (baseline 1.0, settled 0.8, duel winner 1.0) and the prior as one pseudo-observation of
  weight `PRIOR_WEIGHT`; snapped to the garage step and range (existing setup parameter specs), suspension
  coherence via the existing helper; camber at meta. Confidence: effective evidence weight thresholds → low
  / medium / high. First-test suggestion: lowest confidence among wings, diff on, ARBs (in that priority).
- **Fuel:** race = median measured kg/lap on the track (or similar tracks, else the catalogue length ×
  a library-wide kg/km) × the 50 % race laps + 1 lap margin; quali = game minimum.
- **API:** `GET /api/tracks/{track}/generated-setup` → `{profile, setup: {key: {value, display, source,
  confidence, evidence: [...]}}, overall_confidence, first_test, fuel: {quali, race}}`; "make baseline"
  uses step 4's baseline endpoint with `source: "generator"`.
- **Engineer link:** the engineer's start reads the track baseline's source; when it is `generator`, the
  parameter order is re-sorted by the stored per-parameter confidence (low first), keeping the default
  order as the tie-break.
- **React:** the Setups page shows the generated setup when no baseline exists (and on demand otherwise),
  with confidence badges, evidence tooltips / expandable rows, the profile, the first-test suggestion and
  "Make baseline".

## Testing Decisions

- External behaviour only: (1) the estimator on synthetic evidence (similar tracks dominate, prior-only
  gives low confidence and prior values, snapping / ranges / coherence / camber meta, more evidence raises
  confidence); (2) the track profile on real stored corners of library tracks (fractions add up, Monza more
  full-throttle than Monaco/Hungaroring; skip when absent) and from the catalogue for all 28 layouts;
  (3) the API with FastAPI TestClient on a tmp library (with and without baselines; make-baseline);
  (4) an engineer scenario test: generator-sourced baseline → lowest-confidence parameter tested first.
- Frontend helpers (badge mapping, evidence text) get vitest tests; the Setups page is checked in headless
  Chrome on a sandbox library copy.

## Out of Scope

- Machine-learned models; physics simulation.
- Wet / inter setups (the existing weather overlay is not part of this step).
- Generating per-session (quali-only vs race-only) setups — one parc fermé setup.

## Further Notes

- Local-only: commit locally, never push.
- The user chose (2026-10-15) to build this now and flag confidence honestly rather than wait for data.
- Depends on step 3 (stored corners → profile) and step 4 (baselines, duels, Setups page).
