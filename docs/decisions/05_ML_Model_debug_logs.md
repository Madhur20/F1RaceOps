# M5 — ML Tire Degradation Model: Debugging Log

Same format as the M1-M4 logs.

---

### 1. A shuffle warning that would have silently corrupted the train/test split

**Symptom:** running the training pipeline against synthetic test data
(before touching real data) printed:
`UserWarning: you are shuffling a 'StringArray' object which is not a
subclass of 'Sequence'; shuffle is not guaranteed to behave correctly.
E.g., non-numpy array/tensor objects with view semantics may contain
duplicates after shuffling.`

**Root cause:** `df["stint_key"].unique()` returned a pandas
StringArray-backed array rather than a plain numpy object array.
`numpy.random.Generator.shuffle` explicitly warns it may not shuffle this
type correctly — meaning some stints could silently end up duplicated or
missing from the split, which would corrupt the train/test boundary
without any visible error.

**Fix:** converted `unique_stints` to a plain Python list before
shuffling. Caught during initial testing with synthetic data, before ever
running against real ingested laps — worth doing that kind of dry run
before trusting a new pipeline's first real-data result.

---

### 2. The model was mostly learning "which circuit," not "how tires degrade"

**Symptom:** a first version, predicting raw `lap_time_seconds` directly,
showed a reasonable-looking MAE (0.745s) — but feature importances
revealed one circuit's dummy variable alone explained 85% of the model's
predictive power, with `tyre_age` (the entire point of the model)
contributing just 0.2%.

**Root cause:** absolute lap time is dominated by which circuit a lap is
from — Montreal's laps run around 75s, Baku's around 105s — a difference
far larger than any tyre-degradation effect within a stint. With circuit
included as a feature and the target left as raw lap time, the model
could achieve most of its accuracy just by learning circuit identity,
leaving little incentive to learn the smaller, more interesting
tyre_age/compound signal underneath.

**Fix:** de-meaned the training target by each circuit's own average lap
time (computed from training data only, to avoid leaking test-set laps
into the baseline) before fitting. Predictions are added back to the
circuit baseline before computing evaluation metrics, so MAE stays in
interpretable seconds. Verified via a synthetic-data test with a known
noise floor that this changed feature importances dramatically
(tyre_age: 0.2% -> 58.8% on synthetic data) while leaving MAE essentially
unchanged (0.287 -> 0.280) — confirming the fix corrected what the model
was learning without trading away accuracy to do it.

**Why this matters beyond this one model:** this is the same class of
bug as M4 Step 1's circuit-baseline confound in the deterministic
degradation model, showing up independently in a completely different
modeling approach (gradient boosting vs. linear regression). That it
recurred across two very different techniques is a good argument for
treating "does the model's internal reasoning make sense" as a
first-class check for every future model in this project — not just "is
the error metric acceptable."

---

## Takeaway
Both issues here were caught before — or immediately upon — first contact
with real data, not discovered later through a confusing downstream
result. The synthetic-data dry run (item #1) and the habit of inspecting
feature importances rather than trusting MAE alone (item #2) are both
worth carrying into M6's Monte Carlo integration: test the mechanism on
synthetic data with a known right answer before trusting its first output
on real data.