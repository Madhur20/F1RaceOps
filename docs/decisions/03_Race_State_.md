# M3 — Race State Engine: Summary & Decisions

## What was built

`GET /races/{race_id}/state?lap=N` — a full snapshot of the race at a given
lap: each driver's position, gap to leader, gap to the car ahead, tire
compound/age/stint, an estimated fuel level, and the weather conditions
around that point in the race. This is the core input every strategy
simulation from Phase 4 onward will consume.

## Key design decisions

**Gaps are computed from FastF1's own cumulative `Time` field, not by
summing individual lap times.** The first version summed `lap_time_ms`
across laps 1..N per driver — simple, but fragile: a single missing lap
time anywhere in that range (common in real F1 data, especially lap 1)
broke the entire cumulative total for that driver, for every lap for the
rest of the race. Switching to FastF1's own per-lap cumulative elapsed-time
field (stored as `Lap.cumulative_time_ms`, sourced from FastF1's `Time`
column) sidesteps the problem entirely rather than patching around it —
one bad lap for a driver only affects that one lap, not everything after
it.

**The gap-to-leader reference point is "whoever has the lowest complete
cumulative time," not strictly the official P1 driver.** If the actual
race leader's own data has a gap, using their (missing) value as the
reference would null out gap_to_leader for the entire field. In practice,
once gaps switched to the FastF1-native cumulative field, this distinction
rarely matters — but the fallback is documented in code as a known,
deliberate trade-off rather than left implicit.

**Drivers with a null `Position` for one specific lap are kept in the
output, not dropped.** An earlier version filtered out any lap row with a
missing position, which silently erased that driver from the entire
snapshot even though the rest of their data for that lap was fine. Fixed
to sort them to the end with `position: null` instead.

**Fuel remaining is an explicit, labeled estimate, not real telemetry.**
FastF1 doesn't provide fuel load data at all. A simple linear depletion
model (100% at lap 1, 0% at the final lap) fills the field so it's
available as a placeholder input to Phase 4's physics engine, but it's
documented clearly in both the code and the API field name
(`estimated_fuel_remaining_pct`) as an estimate — not something to
present as measured data.

## Verification

Spot-checked two cases where a driver appeared to be "missing" from a
snapshot, to distinguish real data gaps from bugs:

- **2023 Singapore, lap 20**: 19 of 20 drivers shown. Confirmed via
  `race_results.status` that Lance Stroll withdrew from the race —
  correct behavior, not a bug.
- **2023 Azerbaijan, lap 20**: 19 of 20 drivers shown. Confirmed via
  `race_results.status` and a web search that Nyck de Vries retired on
  lap 9 after clipping the Turn 5 wall — correct behavior, not a bug.

Both cases reinforced the same rule: a driver missing entirely from a
snapshot should always be checked against `race_results.status` before
assuming it's a bug — a driver can't have lap data for a lap they never
drove.

## What's next

Phase 4 (M4) — the physics/strategy engine: deterministic tire
degradation, fuel burn, pit-loss, and lap-time models built against this
real data, followed by the ML sub-step (training a degradation model on
real lap data, swappable behind the same interface as the deterministic
one — see the M4 planning discussion for the SWE/DS-ML dual framing).
