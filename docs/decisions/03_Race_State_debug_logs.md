# M3 — Race State Engine: Debugging Log

Same format as the M1 and M2 logs — what went wrong, how it was found, and
how it was fixed, kept while the reasoning is fresh.

---

### 1. Drivers with a null Position silently dropped from the snapshot

**Symptom:** a race state snapshot showed 19 drivers instead of the
expected 20, for a race with no known retirements before that lap.

**Root cause:** the code filtered laps with
`if lap.position is not None` before building the driver list — any driver
whose `Position` field happened to be null for that one specific lap
(an occasional real FastF1 data gap, not a missing lap) was excluded from
the output entirely, rather than included with an unknown position.

**Fix:** kept all drivers with a Lap row at that lap number, sorting
position-null entries to the end instead of dropping them.

---

### 2. One driver's missing data nulled gap_to_leader for the entire field

**Symptom:** in a different race, `gap_to_leader_seconds` was `null` for
every single driver, including the actual P1.

**Root cause:** the reference "leader time" was taken directly from the
official P1 driver's own cumulative time. If that one driver had any
missing lap time in range, their cumulative total was (correctly) `None` —
but every other driver's gap calculation subtracted against that same
`None` value, nulling the field for the whole grid over one driver's data
gap.

**Fix (partial — see #3 for the full fix):** changed the reference point
to the minimum cumulative time among drivers who *do* have complete data,
rather than requiring it to come from the official leader specifically.

---

### 3. The "partial fix" for #2 revealed a much bigger underlying problem

**Symptom:** after the fix for #2, re-testing showed 17 of 19 drivers
still had `null` gaps — and the one non-null "leader" reference was a
P14 driver, not the actual leader.

**Root cause:** the cumulative time itself was being reconstructed by
summing each driver's individual `lap_time_ms` values from lap 1 to N.
That summation is an all-or-nothing calculation: a single missing
`lap_time_ms` anywhere in a driver's first N laps (lap 1 in particular is
often not cleanly timed by FastF1, since it starts from a rolling/standing
start rather than a clean timing-loop crossing) broke that driver's
cumulative total for every subsequent lap of the race. It turned out most
of the field in that particular race had at least one such gap — so the
fix for #2 was correctly working around a symptom while the real disease
(fragile summation) remained.

**Fix:** stopped reconstructing cumulative time altogether. Added a new
column, `Lap.cumulative_time_ms`, sourced directly from FastF1's own `Time`
field (session-elapsed time at the end of each lap, captured natively by
the timing system) rather than derived by summing lap deltas. This
required a schema migration and a full re-ingestion of all 5 races to
backfill the new column, but eliminated the entire class of bug rather
than patching around individual symptoms of it.

---

### 4. (Not a bug) A driver missing from a snapshot due to a real retirement

**Symptom:** 2023 Azerbaijan GP, lap 20 — 19 of 20 drivers shown, same
surface symptom as bug #1.

**Investigation:** checked `race_results.status` for the missing driver
(Nyck de Vries) before assuming a bug, given #1's precedent. Confirmed via
a web search that de Vries retired on lap 9 after clipping the Turn 5 wall
and breaking his front suspension — the same incident that triggered the
safety car that handed Perez the race lead. A driver who retired on lap 9
correctly has no lap 20 data to show.

**Takeaway:** this is the useful contrast to bug #1 — the fix for #1
specifically targeted the case where a driver's Lap *row exists* but a
field on it is null. It does not, and should not, cause a driver with no
Lap row at all (because they genuinely stopped racing) to appear. The
same "driver missing from output" symptom had two different causes across
these four items, and only checking `race_results.status` reliably tells
them apart.

---

## Takeaway
The most valuable lesson from this milestone: fixing #2 without
questioning the deeper assumption behind it (that summing lap times is a
reliable way to get cumulative time) would have shipped a fix that looked
correct in testing but was still fundamentally fragile. Worth treating a
"fix that mostly works" as a prompt to ask whether the underlying approach
is sound, not just whether the symptom went away — especially before
building Phase 4's simulations on top of this data.