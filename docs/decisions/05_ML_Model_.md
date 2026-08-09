# M5 — ML Tire Degradation Model: Summary & Decisions

## What was built
A gradient-boosted regressor (`backend/simulation/tire_models/ml_model.py`)
predicting lap time from tyre_age, lap_number, compound, circuit, and
driver — trained on real lap data across all 5 ingested races, evaluated
on genuinely held-out stints. This is the SWE/DS-ML dual-purpose milestone:
a trained model swapped in as an alternative to the deterministic model
(M4), giving the project a real "trained a model, validated it, compared
it against a baseline" story for data science / ML-focused applications.

## Key methodology decisions

**Evaluation split: random stint-level, not leave-one-race-out.**
Leave-one-race-out was considered and rejected. This project's 5 v1 races
map to 5 *different* circuits (1:1) — leave-one-race-out would always mean
"predict at a circuit the model has zero information about," and with
only 5 circuits total, that measures "how bad is the model with no track
data" rather than the model's actual predictive quality. A random
stint-level split (entire stints held out, never split across train/test,
to avoid leaking a stint's own degradation trend) tests a fairer, more
useful question given this dataset's size: does the model capture
compound/tyre-age/circuit effects well, given it has seen the circuit
before.

**This means the ML model's MAE is NOT directly comparable to the
deterministic model's 0.826s (M4 Step 4).** The two use different
evaluation protocols reflecting different natural deployment scenarios —
the deterministic model recalibrates live from a race's early laps; the
ML model is trained once on historical data and applied to laps it hasn't
specifically seen. Stated explicitly rather than presenting a misleading
single "winner" number.

**The target is de-meaned by circuit baseline before training — a direct
parallel to M4 Step 1's fixed-effects fix.** The first version of this
model predicted raw lap_time_seconds directly, and feature importances
showed one circuit's dummy variable (Montreal) alone explaining 85% of
the model's predictive power, with `tyre_age` at just 0.2% — the model
was almost entirely learning "which circuit is this" rather than anything
about tire degradation, because absolute lap time varies enormously by
circuit (~75s at Montreal vs ~105s at Baku) in a way that swamps the more
subtle degradation signal. Fixed by subtracting each circuit's own average
lap time (computed from training data only, to avoid leakage) from the
training target, forcing the model to learn the *deviation* from a
circuit's baseline rather than the baseline itself. MAE was essentially
unchanged by this fix (0.287 -> 0.280 on a synthetic test, 0.745s ->
0.725s on real data) — confirming it was a pure interpretability fix, not
a predictive-accuracy trade-off; the model was always capable of learning
the real signal, it just had an easier shortcut available before.

## Results (real data, stint-level held-out evaluation)
- 4,898 clean laps across 242 stints, 5 circuits, 28 drivers
- Train: 3,843 laps / 194 stints — Test: 1,055 laps / 48 stints (held out)
- **Mean absolute error: 0.725s**
- **Median absolute error: 0.505s**
- **90th percentile absolute error: 1.547s**

Top feature importances after the de-meaning fix: `lap_number` (48.7%,
plausibly capturing fuel burn-off + track evolution combined),
`tyre_age` (14.8%), several driver codes (5-6% each, plausibly real pace
differences between front-runners and backmarkers), with circuit features
now a minor 1-2% each — a legitimate secondary effect (circuits do have
somewhat different degradation *characters*, not just baseline pace) no
longer dominating the whole model.

## Why this is the right result to lead with, not just "did it work"
The interesting part of M5 isn't that a gradient-boosted model can fit F1
lap times — that was never in doubt. It's that a model with reasonable
overall accuracy (0.745s MAE) was initially learning almost nothing about
the thing it was supposedly modeling (tire degradation), and that this
was only visible by inspecting feature importances rather than trusting
the error metric alone. Same lesson as M4's degradation-model confounds,
now demonstrated on the ML side of the project too: a good aggregate
error number is necessary but not sufficient evidence that a model
learned the right thing.

## What's next
Phase 6 (M6) — wiring the Monte Carlo engine (proven out in the M1 spike)
into a live `/strategy/simulate` endpoint, using the validated
deterministic model (M4) as the primary physics engine, with this ML
model available as a documented, benchmarked alternative.