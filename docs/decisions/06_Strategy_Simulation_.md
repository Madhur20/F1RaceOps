# M6 — Strategy Simulation API: Summary & Decisions

## What was built

The culmination of the whole pipeline: the M1 spike's Monte Carlo mechanism,
rebuilt on the validated M4 models, exposed as a live `POST
/strategy/simulate` endpoint — then extended to support multi-stop
strategies with a different tire compound per stint.

- **`backend/simulation/monte_carlo.py`** — adapts the spike's proven
  mechanics (closed-form vectorized math, common random numbers, a
  safety-car-reactive strategy) to run on real fitted degradation slopes,
  real per-circuit pit-loss models, and the real fuel-effect model, instead
  of the spike's naive single-race fit and placeholder constant.
- **`POST /strategy/simulate`** — live endpoint. For a single remaining
  stop (`n_remaining_stops=1`, the default), returns the same sweep +
  reactive-strategy comparison the spike printed to a terminal, now as
  JSON.
- **Multi-stop extension** — `n_remaining_stops` (default 1, existing
  behavior fully preserved) lets the caller ask for 2+ remaining stops.
  A fast deterministic combinatorial search finds the best set of pit laps
  AND per-stint compound choices; the winning combination is then
  evaluated with a full Monte Carlo pass for real distribution statistics
  (mean, P10, P90).

## Key design decisions

**Trial-to-trial randomness is applied to the degradation SLOPE, not as
generic per-lap noise.** Considered and rejected during design: since
every strategy runs the same number of remaining laps to the finish,
noise applied identically to every strategy in a trial cancels out under
common random numbers — contributing variance to absolute totals but
nothing to "which strategy wins." Noise needs to interact with something
strategy-dependent; randomizing the degradation slope achieves this
because its effect scales with each strategy's own tyre-age sum, which
differs by pit timing.

**The per-trial degradation-slope spread is a stated 30%-of-point-estimate
placeholder, not a measured value.** M4's regression gives the standard
error of the slope estimate — a much smaller quantity reflecting how
precisely the average is pinned down, not how much real stint-to-stint
variability exists around it. Reusing the same heuristic the spike used
for the same reason, flagged explicitly as future work rather than
presented as more rigorous than it is.

**Multi-stop search: cheap deterministic search first, expensive Monte
Carlo evaluation only on the winner.** With 2+ stops the combination
space grows combinatorially (offsets × compound choices). Running the
full trial-level simulation on every candidate would be wasteful;
instead, a closed-form deterministic cost function (no trials, no
randomness) finds the best candidate cheaply, and only that single
winning combination gets the full Monte Carlo treatment for real
risk/distribution statistics.

**The reactive (safety-car-aware) strategy does NOT generalize to
multi-stop in this milestone.** Scoped deliberately: reacting to a safety
car for stop #1 is straightforward, but whether stop #2 should also react
(and how that compounds with stop #1's actual outcome) is a real decision-
tree problem, not a simple rule. `n_remaining_stops>1` currently only
offers the fixed-strategy search, not a reactive variant — stated as a
scope boundary, not silently omitted.

## Two real bugs found during this milestone

**1. Compound choice never picks a faster-but-less-durable compound.**
Given a free choice across compounds, the multi-stop search always
recommended the most durable compound (HARD), never SOFT — because the
model only represents a compound's degradation RATE, with no notion that
softer compounds are also intrinsically faster when fresh (a real,
well-documented effect, ~0.3-0.5s/lap typically). The search logic is
correct; the objective it's optimizing is incomplete. Flagged as a known
limitation — a compound-specific base-pace offset is the natural fix,
not yet implemented.

**2. The multi-stop search recommended INTERMEDIATE (wet) tires for a
completely dry race.** INTERMEDIATE's fitted degradation slope (0.0028
s/lap) was far lower than any dry compound's — not because it's actually
better, but because in the real data it was only ever used briefly during
wet-to-dry transitions, which happen to be low-degradation windows by
their nature. The search, blindly minimizing fitted degradation rate
across every compound with a model, correctly found that number to be
lowest and recommended it — with no concept that a wet-weather compound
is a categorically different tool, not just another point on a
fast-vs-durable spectrum. Fixed by restricting the default candidate set
to dry compounds unless the current compound is already a wet one (a
proxy for "conditions are actually wet," in the absence of live
weather-forecast modeling).

## Why bug #2 is the more important one to remember

Bug #1 is a known, bounded gap — the model is honestly incomplete in a
way that's easy to reason about. Bug #2 is more dangerous precisely
because the output looked confident and well-formed (a clean JSON
response with a specific, plausible-looking recommendation) while being
actively wrong in a way a downstream user might not catch without
domain knowledge. The lesson carried forward from M4 and M5 — "does this
match physical/real-world intuition" as a first-class check, not just
"does the code run" — caught this one too, and it's worth treating any
model output that recommends something a real strategist would consider
absurd as a signal to investigate the objective function, not just the
number.

## What's next

Write up and validate multi-stop results across more scenarios; consider
the compound-pace-offset fix; Phase 7/8 (M7/M8) — dashboard, testing, CI.
