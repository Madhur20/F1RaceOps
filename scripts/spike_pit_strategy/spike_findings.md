# M1 Spike — Findings

## Purpose
Prove the core simulation idea works and is genuinely interesting *before*
investing weeks building the full data layer around it. No database, no API —
just FastF1 → naive model → Monte Carlo → terminal output.

## Method
- Loaded real race-lap data for a single driver in a single race (2023
  Bahrain GP, VER) via FastF1, filtered to accurate, non-reconstructed laps.
- Fit a naive per-stint linear degradation model directly from that data:
  `lap_time = base_lap_time + deg_slope × tyre_age`, averaged across stints
  and weighted by stint length.
- Given a mid-race snapshot (current lap, current tyre age), evaluated two
  kinds of pit strategy using Monte Carlo simulation with common random
  numbers (same degradation draw, pit-stop-duration draw, and per-lap
  safety-car occurrences shared across every strategy compared, so
  differences reflect real strategic effects rather than random noise):
  - A **sweep** of every fixed pit-lap offset (0 to ~20 laps ahead), to see
    the full cost curve and its true minimum.
  - A **reactive** strategy: watch the next N laps for a safety car; pit
    immediately at a discount if one appears, otherwise fall back to a fixed
    offset.

## Results
- The cost curve across fixed offsets is smooth and convex, with a clear
  single minimum — e.g., from lap 20 (tyre age 15) in a 57-lap race, +10/+11
  laps out was optimal, with total time rising smoothly on both sides.
- Head-to-head, Reactive vs. the best fixed strategy (5,000 trials, current
  lap 20):
  - **~76% ties** — no safety car appeared in the reactive window, so it
    fell back to the same lap as the fixed strategy; no real difference.
  - **~21% Reactive wins** — a safety car appeared within the reactive
    window, and pitting opportunistically at the discount beat the committed
    fixed plan.
  - **~3% Fixed wins** — an edge case where a safety car happened to land
    exactly on the fixed strategy's pit lap (outside the reactive window),
    giving it a discount the reactive strategy's fallback didn't check for.
  - The ~21% reactive-win rate lines up closely with the theoretical chance
    of a safety car occurring within an 8-lap window at a 3%/lap rate
    (`1 - 0.97^8 ≈ 22%`), which is a good sanity check that the mechanism is
    behaving the way the math says it should.

## What this validates
- The FastF1 → model → Monte Carlo → decision pipeline works end to end on
  real data.
- The simulation produces a genuine, non-obvious, quantifiable insight
  (adaptive strategy has a real, measurable edge over a committed plan when
  conditions can change) rather than noise — this is the core product idea,
  and it's interesting enough to be worth building the full platform around.

## Known limitations (by design, not oversights — deferred to later phases)
- **Single pit stop only.** Real races often involve two or more stops;
  multi-stop optimization is a materially harder problem, deferred to a
  later phase.
- **No rival/track-position awareness.** The model optimizes in isolation;
  it has no concept of undercutting, traffic on pit exit, or race position.
- **Degradation fit from one driver, one race.** Not a general degradation
  fact — specific to this driver/compound/track/conditions. Different
  driver or race will likely produce a different optimal lap.
- **Safety car probability (3%/lap) is a placeholder**, not fit to real
  historical per-circuit rates. Phase 4 should replace this with actual
  historical SC frequency by circuit.
- **No compound-specific degradation.** Soft/medium/hard tires degrade at
  very different rates; the naive model pools all stints into one line.

## Next step
Move to Phase 2 (real data layer: ingestion for all 5 v1 races, Postgres
schema, first API endpoints), now that the core mechanism is validated.