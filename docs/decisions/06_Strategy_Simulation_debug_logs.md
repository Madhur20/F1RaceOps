# M6 — Strategy Simulation API: Debugging Log

Same format as the M1-M5 logs.

---

### 1. (Caught before running) Noise that would have cancelled out uselessly

**Symptom:** none — caught during design, before writing the strategy-
comparison code.

**Near-miss:** the first instinct was to add generic per-lap noise
(using the degradation model's residual spread) to make the simulation
more realistic. Reasoning it through: since every strategy runs the same
number of remaining laps, noise applied identically to every strategy in
a trial would cancel out entirely under common random numbers — adding
variance to absolute totals but contributing nothing to which strategy
wins, making it pointless for the actual comparison being made.

**Fix:** kept the spike's proven approach — randomize the degradation
slope itself per trial, so its effect scales with each strategy's own
(strategy-dependent) tyre-age sum, preserving real discriminating power
in the comparison.

---

### 2. Compound choice systematically ignored SOFT tires

**Symptom:** the multi-stop search, given a completely free choice of
compound for future stints, always chose the most durable option (HARD)
— never SOFT, regardless of how short the remaining stint was.

**Root cause:** the model represents compound only via degradation RATE.
It has no notion that softer compounds are also faster when fresh (a
real, separate effect from how quickly they wear) — so the model sees
only downside to choosing SOFT and no upside, making HARD the
mathematically dominant choice in every scenario tested.

**Status:** documented as a known limitation, not yet fixed. A
compound-specific base-pace offset would be the natural repair.

---

### 3. The multi-stop search recommended wet tires for a dry race

**Symptom:** asking for a 2-stop strategy at Bahrain 2023 (a dry race)
returned a recommendation to run INTERMEDIATE tires for both remaining
stints.

**Root cause:** INTERMEDIATE's fitted degradation slope (0.0028 s/lap)
was far lower than any dry compound's — an artifact of when it was used
in the real data (briefly, during wet-to-dry transitions, inherently
low-degradation windows), not evidence it performs well in the dry. The
search minimized fitted degradation rate across every compound with a
model, with no awareness that a wet-weather compound is a categorically
different tool rather than a point on the same fast-vs-durable spectrum
as the dry compounds.

**Fix:** the default candidate-compound set now excludes wet compounds
unless the CURRENT compound is already a wet one — a heuristic proxy for
"conditions are actually wet," given the absence of live weather-forecast
modeling. An explicit `allowed_compounds` override still lets a caller
deliberately include wet compounds if they want to.

**Verification:** re-tested three scenarios after the fix — starting on
a dry compound (correctly excludes INTERMEDIATE by default), an explicit
override (correctly still allows it when asked for), and starting on
INTERMEDIATE itself (correctly keeps all compounds eligible, since
conditions are plausibly wet).

---

## Takeaway

Bug #3 is the standout finding of this milestone, and it's worth stating
plainly why: the output wasn't obviously broken — it was a clean,
well-formed JSON response with a specific, confident-looking
recommendation. Nothing about the response's _shape_ signaled a problem;
only checking it against real-world domain knowledge ("would a strategist
ever actually do this") surfaced the issue. Every debugging log in this
project has pointed at some version of this same lesson, and it keeps
paying off: a model that runs without error and returns well-typed,
validated JSON has cleared a much lower bar than "the output is actually
correct," and the two should never be conflated.
