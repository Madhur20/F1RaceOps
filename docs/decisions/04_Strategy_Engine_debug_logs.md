# M4 — Physics/Strategy Engine: Debugging Log

Same format as the M1-M3 logs. Most of M4's real bug-hunting happened in
Step 1 (the degradation model) — full detail in
[`docs/m4-degradation-model.md`](./m4-degradation-model.md). Summarized
here for completeness, alongside two design pitfalls caught and avoided
in later steps before they became bugs.

---

### 1. Tyre-age and fuel-burn were unidentifiable within a single stint

**Symptom:** MEDIUM and HARD compounds showed negative degradation slopes
— lap times appearing to get faster as tyres aged.

**Root cause:** within one stint, `tyre_age` and `lap_number` differ only
by a constant, so a per-stint regression cannot separate "tyres degrading"
from "fuel burning off" — they produce identical predictions from that
stint's data alone.

**Fix:** pool laps across all stints of a compound before fitting, since
different stints reset `tyre_age` at different `lap_number` values,
providing the variation needed to separate the two effects.

_(Full detail: docs/m4-degradation-model.md)_

---

### 2. Circuit baseline pace confounded compound comparisons

**Symptom:** after fix #1, HARD still showed steeper degradation than
SOFT — physically backwards.

**Root cause:** compound choice correlates with circuit (harder compounds
at abrasive tracks, softer at smooth ones), so the pooled fit was partly
capturing "which circuit" rather than "which compound."

**Fix:** added per-race fixed effects (a dummy variable per race) to the
regression, safe to add without breaking fix #1 since multiple stints
still exist within a single race.

_(Full detail: docs/m4-degradation-model.md)_

---

### 3. (Caught before running) Double-counting the fuel effect

**Symptom:** none — caught during design of Step 4, before writing the
combined model.

**Near-miss:** the degradation regression (Step 1) already fits a
`fuel_slope` coefficient as part of controlling for fuel burn-off. Step 3
separately built a physics-based fuel model. Combining the degradation
model's fitted fuel effect AND the standalone physics-based fuel effect
in the same lap-time prediction would have double-counted fuel burn-off,
silently inflating the predicted effect of a full tank.

**Fix:** explicit design decision, stated in code: use only the Step 3
physics-based fuel model in the combined predictor. The regression's
`fuel_slope` exists solely to correctly isolate the degradation slope
during fitting and is not reused as a standalone predictive value.

---

### 4. (Caught before running) A private helper used across module

boundaries

**Symptom:** none — a code-quality issue, not a runtime bug.

**Near-miss:** `get_excluded_lap_keys` (identifying pit in/out laps)
started as an underscore-prefixed "private" function in the degradation
model module. Step 4's base-pace estimation needed the identical logic,
and importing a private helper across modules is a habit worth stopping
early rather than letting it normalize.

**Fix:** promoted to a public, shared utility.

---

## Takeaway

Compared to M2 and M3, more of this milestone's problems were caught by
design review before they became runtime bugs (items #3 and #4) rather
than discovered by re-running against real data (items #1 and #2). Both
routes are legitimate, but #1 and #2 are the more valuable lesson: a
result that looks physically wrong (negative degradation, backwards
compound ordering) is a stronger and faster signal than waiting for a
crash or an obviously bad number — worth treating "does this match
physical intuition" as a first-class check alongside "does the code run
without error" for every future model in this project.
