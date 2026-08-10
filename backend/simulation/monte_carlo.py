"""
F1RaceOps — Monte Carlo pit-strategy simulator.

Adapts the M1 spike's proven mechanics (closed-form vectorized math, common
random numbers, a safety-car-reactive strategy) to run on the validated M4
models instead of the spike's naive single-race degradation fit and
placeholder pit-loss constant.

DESIGN NOTE — why trial-to-trial randomness is applied to the degradation
SLOPE, not as generic per-lap noise: since every strategy runs the same
number of remaining laps to the finish, noise applied identically to every
strategy in a trial cancels out under common random numbers — it would add
variance to absolute totals but contribute nothing to "which strategy
wins," making it pointless for strategy comparison. Noise needs to
interact with something strategy-DEPENDENT. Randomizing the degradation
slope achieves this because its effect scales with each strategy's own
tyre-age sum, which differs by pit timing — same mechanism the M1 spike
used, now driven by the real fitted M4 slope.

KNOWN PLACEHOLDER: the per-trial degradation slope spread uses a flat 30%-
of-point-estimate heuristic (same one the spike used for single-stint
variance, and the same one deterministic.py falls back to when a compound
has only one contributing stint). M4's regression gives the STANDARD ERROR
of the slope estimate, which is a different, much smaller quantity — it
reflects how precisely we've pinned down the average, not how much real
stint-to-stint variability (track evolution, tyre batch, driver
management) exists around it. The 30% heuristic is a stated placeholder,
not a measured value; a real fix would separately estimate per-stint
residual spread, deferred as future work rather than done here.

Also unchanged from the spike, for the same reason (no data to fit it
from): safety car probability is a flat per-lap placeholder, not fit to
real historical per-circuit rates.
"""

from dataclasses import dataclass

import numpy as np

from backend.simulation.fuel_model import estimate_fuel_effect
from backend.simulation.lap_time_model import LapTimePredictor
from backend.simulation.pit_loss_model import PitLossModel

# Compound categories — not just "fast vs. durable," but genuinely different
# tools. A wet-weather compound having a low fitted degradation slope (often
# true, since it's typically only used briefly during wet-to-dry transitions
# in the data) is NOT evidence it's a good choice in the dry — it would
# actually be slower and behave worse. The search must not treat compound
# choice as one continuous spectrum without this distinction.
DRY_COMPOUNDS = {"SOFT", "MEDIUM", "HARD"}
WET_COMPOUNDS = {"INTERMEDIATE", "WET"}


def _default_allowed_compounds(predictor: LapTimePredictor, current_compound: str) -> list[str]:
    """
    Defaults to dry compounds only, UNLESS the current compound is already a
    wet one — a reasonable signal that wet conditions are actually in play
    for this scenario, in which case wet compounds stay eligible too. This
    project has no live weather-forecast modeling, so this heuristic (infer
    from the current compound) is a deliberate, explainable stand-in rather
    than a fully weather-aware selection.
    """
    fitted = set(predictor.degradation_models.keys())
    if current_compound in WET_COMPOUNDS:
        return list(fitted)  # already wet — don't rule out staying wet or drying out
    return list(fitted & DRY_COMPOUNDS)
DEG_SLOPE_UNCERTAINTY_FRACTION = 0.30
SAFETY_CAR_PROB_PER_LAP = 0.03
SAFETY_CAR_PIT_LOSS_MULTIPLIER = 0.35


@dataclass
class CommonRandomNumbers:
    deg_slope_per_trial: np.ndarray      # (n_trials,)
    pit_loss_per_trial: np.ndarray       # (n_trials,) — green-flag cost, SC discount applied per-strategy
    sc_lap_flags: np.ndarray             # (n_trials, remaining_laps) bool


def generate_common_random_numbers(
    deg_slope: float, remaining_laps: int, n_trials: int,
    pit_loss_model: PitLossModel, rng: np.random.Generator,
) -> CommonRandomNumbers:
    deg_slope_std = abs(deg_slope) * DEG_SLOPE_UNCERTAINTY_FRACTION
    deg_slope_per_trial = rng.normal(deg_slope, deg_slope_std, size=n_trials)

    pit_loss_per_trial = rng.normal(pit_loss_model.mean_seconds, pit_loss_model.std_seconds, size=n_trials)
    sc_lap_flags = rng.random((n_trials, remaining_laps)) < SAFETY_CAR_PROB_PER_LAP

    return CommonRandomNumbers(deg_slope_per_trial, pit_loss_per_trial, sc_lap_flags)


def _fuel_effects_sum(current_lap: int, remaining_laps: int, total_laps: int) -> float:
    """Fuel effect depends only on absolute lap number, not on pit timing —
    identical across every strategy being compared, so computed once."""
    return sum(
        estimate_fuel_effect(current_lap + offset, total_laps).lap_time_delta_seconds
        for offset in range(1, remaining_laps + 1)
    )


def _total_time_for_offset(
    base_pace: float, remaining_laps: int, current_tyre_age: int,
    offset, fuel_effects_sum: float, crn: CommonRandomNumbers,
) -> np.ndarray:
    """
    Closed-form total race time for pitting after `offset` more laps —
    `offset` may be a python int (same for all trials, the sweep case) or a
    numpy array (a different effective offset per trial, the reactive
    case). Same arithmetic-sequence closed form as the M1 spike, extended
    with base_pace and the fuel-effect sum (both absent from the spike's
    naive model).
    """
    pre_terms = offset
    pre_sum_age = pre_terms * current_tyre_age + pre_terms * (pre_terms - 1) / 2
    post_terms = remaining_laps - offset
    post_sum_age = post_terms * (post_terms - 1) / 2
    sum_age = pre_sum_age + post_sum_age

    lap_time_total = remaining_laps * base_pace + crn.deg_slope_per_trial * sum_age + fuel_effects_sum
    return lap_time_total + crn.pit_loss_per_trial


def simulate_sweep(
    predictor: LapTimePredictor, pit_loss_model: PitLossModel,
    base_pace: float, compound: str, current_tyre_age: int, current_lap: int,
    race_total_laps: int, max_offset: int, n_trials: int, rng: np.random.Generator,
) -> tuple[dict[int, np.ndarray], CommonRandomNumbers]:
    remaining_laps = race_total_laps - current_lap
    max_offset = min(max_offset, remaining_laps - 1)
    deg_slope = predictor.get_degradation_slope(compound)
    fuel_sum = _fuel_effects_sum(current_lap, remaining_laps, race_total_laps)

    crn = generate_common_random_numbers(deg_slope, remaining_laps, n_trials, pit_loss_model, rng)

    results = {}
    for offset in range(0, max_offset + 1):
        sc_on_pit_lap = crn.sc_lap_flags[:, offset]
        # apply SC discount to a COPY of pit_loss_per_trial for this offset —
        # crn.pit_loss_per_trial itself must stay untouched, shared across offsets
        pit_loss = np.where(sc_on_pit_lap,
                             crn.pit_loss_per_trial * SAFETY_CAR_PIT_LOSS_MULTIPLIER,
                             crn.pit_loss_per_trial)
        crn_for_offset = CommonRandomNumbers(crn.deg_slope_per_trial, pit_loss, crn.sc_lap_flags)
        results[offset] = _total_time_for_offset(
            base_pace, remaining_laps, current_tyre_age, offset, fuel_sum, crn_for_offset,
        )

    return results, crn


def simulate_reactive(
    predictor: LapTimePredictor, pit_loss_model: PitLossModel,
    base_pace: float, compound: str, current_tyre_age: int, current_lap: int,
    race_total_laps: int, window: int, fallback_offset: int,
    n_trials: int, crn: CommonRandomNumbers,
) -> np.ndarray:
    """Shares the SAME crn object as simulate_sweep (passed in, not
    regenerated) — required for a valid common-random-numbers comparison
    between the sweep's strategies and this one."""
    remaining_laps = race_total_laps - current_lap
    fuel_sum = _fuel_effects_sum(current_lap, remaining_laps, race_total_laps)

    sc_window = crn.sc_lap_flags[:, :window]
    found_sc = sc_window.any(axis=1)
    first_sc_lap = np.argmax(sc_window, axis=1)
    effective_offset = np.where(found_sc, first_sc_lap, fallback_offset)

    pit_loss = np.where(found_sc,
                         crn.pit_loss_per_trial * SAFETY_CAR_PIT_LOSS_MULTIPLIER,
                         crn.pit_loss_per_trial)
    crn_reactive = CommonRandomNumbers(crn.deg_slope_per_trial, pit_loss, crn.sc_lap_flags)

    return _total_time_for_offset(
        base_pace, remaining_laps, current_tyre_age, effective_offset, fuel_sum, crn_reactive,
    )


# ---------------------------------------------------------------------------
# Multi-stop strategies (n_stops >= 1). n_stops=1 is handled entirely by the
# functions above and is unaffected by anything below — this section only
# activates for n_stops >= 2.
# ---------------------------------------------------------------------------

def _deterministic_multi_stop_cost(
    base_pace: float, predictor: LapTimePredictor, pit_loss_mean: float,
    current_tyre_age: int, remaining_laps: int, offsets: tuple[int, ...],
    stint_compounds: tuple[str, ...], fuel_effects_sum: float,
) -> float:
    """
    Mean-case (no trial-level randomness) total time for a FIXED sequence of
    pit-lap offsets AND a compound choice per stint. `stint_compounds` has
    length len(offsets) + 1 — one compound per segment, including the
    current one (segment 0). Generalizes the single-compound version by
    applying each segment's OWN degradation slope to that segment's own
    tyre-age sum, rather than one slope for the whole strategy.

    Used only for the fast deterministic search below — NOT for reporting
    final statistics, which come from simulate_multi_stop's full Monte
    Carlo evaluation instead.
    """
    total_deg_cost = 0.0
    prev_offset = 0
    prev_age = current_tyre_age
    for i, o in enumerate(offsets):
        seg_len = o - prev_offset
        seg_sum_age = seg_len * prev_age + seg_len * (seg_len - 1) / 2
        total_deg_cost += predictor.get_degradation_slope(stint_compounds[i]) * seg_sum_age
        prev_offset = o
        prev_age = 0  # tyre resets after every stop
    final_seg_len = remaining_laps - prev_offset
    final_seg_sum_age = final_seg_len * prev_age + final_seg_len * (final_seg_len - 1) / 2
    total_deg_cost += predictor.get_degradation_slope(stint_compounds[-1]) * final_seg_sum_age

    return (remaining_laps * base_pace + total_deg_cost
            + fuel_effects_sum + len(offsets) * pit_loss_mean)


def find_best_fixed_multi_stop(
    predictor: LapTimePredictor, pit_loss_model: PitLossModel,
    base_pace: float, current_compound: str, current_tyre_age: int, current_lap: int,
    race_total_laps: int, n_stops: int, allowed_compounds: list[str] | None = None,
) -> tuple[tuple[int, ...], tuple[str, ...], float]:
    """
    Fast deterministic search over all valid combinations of n_stops pit-lap
    offsets AND compound choices for each future stint, returning the
    lowest-mean-cost combination. `current_compound` is fixed for the first
    segment (can't change what's already on the car) — only future stints'
    compounds are searched.

    `allowed_compounds` defaults to every compound with a fitted degradation
    model (predictor.degradation_models) — e.g. if WET has no fitted model
    in the current dataset, it's automatically excluded rather than
    silently treated as zero-degradation.

    Same "cheap deterministic search, then expensive Monte Carlo evaluation
    of only the winner" principle as the single-compound version and the
    single-stop sweep before it.
    """
    import itertools

    if allowed_compounds is None:
        allowed_compounds = _default_allowed_compounds(predictor, current_compound)
        if not allowed_compounds:
            raise ValueError("No compounds have a fitted degradation model — cannot search.")

    remaining_laps = race_total_laps - current_lap
    fuel_sum = _fuel_effects_sum(current_lap, remaining_laps, race_total_laps)

    best_cost = float("inf")
    best_offsets: tuple[int, ...] | None = None
    best_compounds: tuple[str, ...] | None = None

    for offset_combo in itertools.combinations(range(0, remaining_laps), n_stops):
        for compound_combo in itertools.product(allowed_compounds, repeat=n_stops):
            stint_compounds = (current_compound,) + compound_combo
            cost = _deterministic_multi_stop_cost(
                base_pace, predictor, pit_loss_model.mean_seconds,
                current_tyre_age, remaining_laps, offset_combo, stint_compounds, fuel_sum,
            )
            if cost < best_cost:
                best_cost = cost
                best_offsets = offset_combo
                best_compounds = stint_compounds

    return best_offsets, best_compounds, best_cost


def simulate_multi_stop(
    predictor: LapTimePredictor, pit_loss_model: PitLossModel,
    base_pace: float, current_tyre_age: int, current_lap: int,
    race_total_laps: int, offsets: tuple[int, ...], stint_compounds: tuple[str, ...],
    n_trials: int, rng: np.random.Generator,
) -> np.ndarray:
    """
    Full Monte Carlo evaluation of a SPECIFIC fixed multi-stop, multi-
    compound strategy. `stint_compounds` has length len(offsets) + 1 (one
    per segment, including the current one). Each segment draws its OWN
    independent per-trial degradation-slope noise — even two stints on the
    same compound are treated as independently variable (different tyre
    sets genuinely wear differently stint to stint), not given identical
    noise.

    Generates its own common random numbers sized for len(offsets)
    independent pit-loss draws — this evaluates ONE strategy's own risk
    distribution, not comparing multiple strategies against each other, so
    it doesn't need to share CRN with anything else.
    """
    remaining_laps = race_total_laps - current_lap
    fuel_sum = _fuel_effects_sum(current_lap, remaining_laps, race_total_laps)

    n_segments = len(stint_compounds)
    deg_slopes_per_segment = []
    for compound in stint_compounds:
        slope = predictor.get_degradation_slope(compound)
        slope_std = abs(slope) * DEG_SLOPE_UNCERTAINTY_FRACTION
        deg_slopes_per_segment.append(rng.normal(slope, slope_std, size=n_trials))

    pit_loss_per_trial = rng.normal(
        pit_loss_model.mean_seconds, pit_loss_model.std_seconds, size=(n_trials, len(offsets))
    )
    sc_lap_flags = rng.random((n_trials, remaining_laps)) < SAFETY_CAR_PROB_PER_LAP

    total_deg_cost = np.zeros(n_trials)
    total_pit_loss = np.zeros(n_trials)
    prev_offset = 0
    prev_age = current_tyre_age
    for i, o in enumerate(offsets):
        seg_len = o - prev_offset
        seg_sum_age = seg_len * prev_age + seg_len * (seg_len - 1) / 2
        total_deg_cost += deg_slopes_per_segment[i] * seg_sum_age

        sc_on_this_stop = sc_lap_flags[:, o]
        stop_loss = np.where(sc_on_this_stop,
                              pit_loss_per_trial[:, i] * SAFETY_CAR_PIT_LOSS_MULTIPLIER,
                              pit_loss_per_trial[:, i])
        total_pit_loss += stop_loss
        prev_offset = o
        prev_age = 0
    final_seg_len = remaining_laps - prev_offset
    final_seg_sum_age = final_seg_len * prev_age + final_seg_len * (final_seg_len - 1) / 2
    total_deg_cost += deg_slopes_per_segment[-1] * final_seg_sum_age

    lap_time_total = remaining_laps * base_pace + total_deg_cost + fuel_sum
    return lap_time_total + total_pit_loss