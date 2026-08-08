# M4 — Physics/Strategy Engine: Summary & Decisions

## What was built

The deterministic "physics engine" the Phase 4 plan called for: three
component models (tire degradation, pit-loss, fuel effect) fit or derived
independently, then combined into a single lap-time predictor and
validated against real, held-out race data.

- **Step 1 — Tire degradation model** (`backend/simulation/tire_models/deterministic.py`):
  per-compound degradation slope, fit from real lap data across all 5
  races. See [`docs/m4-degradation-model.md`](./m4-degradation-model.md)
  for the full write-up — this step surfaced the milestone's two most
  interesting bugs (summarized below).
- **Step 2 — Pit-loss model** (`backend/simulation/pit_loss_model.py`):
  real mean/std pit-lane loss per circuit, fit from the `pit_stops` table,
  replacing the M1 spike's flat placeholder (22.5s for every circuit).
- **Step 3 — Fuel-effect model** (`backend/simulation/fuel_model.py`): a
  textbook physics approximation (~0.03s per kg, 110kg starting load,
  linear burn-off) — NOT fit from data, since FastF1 exposes no fuel
  telemetry at all. Deliberately kept separate in status from the two
  fitted models.
- **Step 4 — Combined lap-time model** (`backend/simulation/lap_time_model.py`):
  `predicted_lap_time = driver_base_pace + degradation_effect + fuel_effect`,
  with base pace backed out per-driver from their own early-stint laps.
  Validated against real held-out laps (see Results below).

## Key design decisions

**Pit-loss outliers are filtered per circuit via IQR, not a fixed
cutoff.** Normal pit-lane loss itself varies meaningfully by circuit (a
long pit lane has a different baseline than a short one), so a single
global threshold would have misclassified normal stops at some circuits
as outliers and left real outliers (drive-through penalties, damage
stops) in at others.

**The fuel model is a stated approximation, not a fitted model — and this
distinction is preserved through the whole pipeline.** The
`FuelEffectEstimate` dataclass and every docstring referencing it makes
clear this number has no standard error or confidence interval the way
the degradation and pit-loss models do, because it isn't derived from
this project's data at all.

**The combined model deliberately does NOT use the degradation
regression's fitted `fuel_slope`, even though one exists.** That
coefficient was fit only to control for fuel burn-off while isolating the
tyre-age effect (see Step 1) — it's pooled across circuits and stint
lengths in a way that makes it unreliable as a standalone predictive fuel
model for an arbitrary race length. The physics-based Step 3 model is
used instead, and this choice is stated explicitly in code rather than
left as an implicit, easy-to-miss inconsistency between two "fuel-ish"
numbers living in the same codebase.

**Base pace is backed out from each driver's early, low-tyre-age laps**
(tyre_life <= 3), by subtracting the estimated fuel effect and near-zero
degradation contribution from their actual lap times. This is itself an
approximation — it assumes the degradation model is accurate at very low
tyre ages and that a handful of early laps is enough to estimate a stable
per-driver, per-race baseline.

## Validation results

`scripts/validate_lap_time_model.py` estimates base pace from each
driver's early laps only, then predicts lap times for their _later_ laps
(tyre_life > 3, never used to fit anything) and compares against what
actually happened — genuine held-out validation, not a fit-then-check-the-
same-data sanity test.

Across all 5 races and ~19-20 drivers each:

- **Mean absolute error: 0.826s**
- **Median absolute error: 0.614s**
- **90th percentile absolute error: 1.788s**

For real F1 lap times in the 75-108s range, sub-second median error from
a first-order linear model with no traffic, driver-error, or track-
evolution terms is a solid result. The pattern of errors across races is
itself informative: Singapore (the safety-car-prone circuit) shows the
weakest fit, plausibly because safety-car/VSC laps run at a very different
pace than green-flag racing, which this model doesn't yet account for —
a reasonable, explainable limitation rather than a mystery.

## Refactor along the way

`get_excluded_lap_keys` (identifying pit in-laps/out-laps to exclude from
degradation fitting) was originally a private, underscore-prefixed helper
inside the degradation model module. Once the combined lap-time model
(Step 4) needed the same logic for base-pace estimation, it was promoted
to a shared public utility rather than left as one module reaching into
another's "private" internals — a small thing, but worth doing before it
became a habit.

## What's next

Phase 5 (M5) — an ML tire degradation model trained on real lap data,
compared against this deterministic version (the SWE/DS-ML dual-purpose
milestone). Phase 6 (M6) — wiring the Monte Carlo engine (proven out in
the M1 spike) into a live `/strategy/simulate` endpoint, now running on
top of these validated models instead of the spike's naive single-race fit.
