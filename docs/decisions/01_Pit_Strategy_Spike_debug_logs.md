# M1 Spike — Debugging Log

Kept deliberately as a record of what went wrong and how it was diagnosed —
this kind of trail is easy to lose once a bug is fixed, and it's genuinely
useful for interview conversations about debugging methodology, not just the
final result.

---

### 1. "Pit Now" never actually pitted (off-by-one in loop indexing)

**Symptom:** "Pit Now" won the strategy comparison almost every time, with
its win probability climbing toward ~89% as the current lap advanced —
suspiciously one-sided for a real strategic decision.

**Root cause:** the pit condition compared an absolute lap number
(`pit_lap = current_lap + offset`) against a loop variable that only ever
enumerated *future* laps starting at `current_lap + 1`. For `offset = 0`
("Pit Now"), `pit_lap` equaled `current_lap`, which the loop never reached —
so "Pit Now" silently never triggered a pit stop or paid its cost. It was
effectively simulating "never pit," which wins by construction since it
skips the ~22.5s pit-lane loss entirely.

**Fix:** rewrote the pit condition to compare against the loop's *relative*
position instead of an absolute lap number, so `offset = 0` correctly
triggers on the very first simulated lap.

---

### 2. Fixing bug #1 exposed a stale, physically inconsistent test scenario

**Symptom:** after fixing #1, results still looked off — because test runs
were using `--current-tyre-age 15` (the default) even at `--current-lap 5`,
which isn't physically possible (can't have 15 laps of wear 5 laps into the
race).

**Fix:** no code change — just running scenarios with tyre age consistent
with the chosen current lap.

---

### 3. Independent RNG streams meant "paired" trials weren't actually paired

**Symptom:** after fixing #1 and #2, all three strategies (Pit Now/+1/+2)
converged to a ~33/33/33 win-probability split — no signal at all, even
though the real degradation-driven differences between strategies should
have been visible.

**Root cause:** each strategy's simulation drew its own randomness from a
shared `rng` object, but called it independently — so "trial `i`" for one
strategy and "trial `i`" for another consumed entirely different, unrelated
positions in the random stream. The comparison was structured to look
paired (same array index) but wasn't actually paired (same underlying random
draws). The real signal (~1-2s difference between strategies) was swamped by
unrelated per-trial noise (~25-30s standard deviation).

**Fix:** switched to common random numbers — degradation slope, pit-stop
duration, and (later) per-lap safety-car flags are now drawn once per trial
and explicitly shared across every strategy being compared, so trial `i`
means the same simulated race for all of them.

---

### 4. Reactive strategy had the best mean time but a 0% win rate

**Symptom:** after adding the reactive (safety-car-aware) strategy and
comparing it against the full sweep of fixed offsets, its mean time was
the lowest of any strategy — yet it won zero trials.

**Root cause:** when the reactive strategy's SC-triggered pit lap happened
to match one of the swept fixed offsets on the same trial, both computed
the *exact same* total time (same offset, same discount, same underlying
draws). `np.argmin`'s tie-breaking always favors the first matching column,
and the fixed-offset columns came before the reactive column in the
comparison matrix — so every tie silently resolved in favor of the fixed
strategy, masking the cases where reactive was genuinely just as good.

**Fix:** replaced the confounded all-strategies comparison with a clean
head-to-head: reactive vs. only the single best fixed offset found by the
sweep, with ties reported explicitly rather than silently absorbed into one
side's win count.

---

### 5. Reactive strategy crashed with very few laps remaining

**Symptom:** `--current-lap 56 --current-tyre-age 28` (1 lap remaining in a
57-lap race) crashed with `ValueError: attempt to get argmax of an empty
sequence`.

**Root cause:** the reactive window was clamped using the same `- 1` logic
as the fixed-offset sweep (`min(window, remaining_laps - 1)`), which was
correct for the sweep — where an offset is used as a direct array index and
must stay under `remaining_laps` — but unnecessarily strict for the
reactive window, which is used as a *slice* bound and can validly reach all
the way to `remaining_laps`. With exactly 1 lap remaining, the clamp forced
the window to 0, producing an empty slice that `np.argmax` can't operate on.

**Fix:** clamped the window to `remaining_laps` (not `remaining_laps - 1`),
floored at 1, and added an explicit early validation error for the
degenerate case where no laps remain at all.

---

## Takeaway
Every one of these was a real correctness bug in the simulation logic, not
a cosmetic issue — several of them silently produced plausible-looking but
wrong results (bugs #1, #3, and #4 all still printed clean, well-formatted
tables). Worth remembering going into Phase 2-4: a Monte Carlo sim can be
syntactically fine and numerically confident while being quietly wrong, so
sanity-checking *why* a result looks the way it does (not just whether the
code runs) has to stay part of the workflow, not a one-time spike exercise.