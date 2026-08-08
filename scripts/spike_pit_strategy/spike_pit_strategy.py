"""
Spike: Pit Strategy Monte Carlo (single race, terminal output only)

Goal: prove the core idea works before building the full data layer. No
database, no API — just FastF1 -> pandas -> naive model -> Monte Carlo ->
printed strategy comparison.

Usage:
    python spike_pit_strategy.py --year 2023 --event Bahrain --driver VER \
        --current-lap 20 --current-tyre-age 15 --n-trials 5000

What it does:
    1. Loads real lap data for one driver in one race via FastF1.
    2. Fits a naive linear tire-degradation model directly from that
       driver's real stint data (lap_time vs tyre age).
    3. Given a mid-race snapshot, evaluates:
         a) a SWEEP of fixed pit-lap offsets (0..--sweep-max-offset), to see
            the actual cost curve and its true minimum, not just 3 points
         b) a REACTIVE strategy: watch the next --reactive-window laps for a
            safety car; pit immediately (cheaply) if one appears, otherwise
            fall back to pitting at --reactive-fallback-offset
       All strategies are compared using COMMON RANDOM NUMBERS — the same
       per-trial degradation draw and per-lap safety-car draws are reused
       across every strategy, so trial i means "the same simulated race" for
       all of them. This is what makes the win-probability comparison valid;
       without it, real (often small) differences between strategies get
       swamped by unrelated noise.
    4. Prints the full sweep (mean time per offset) plus a win-probability
       table across the sweep + the reactive strategy.
"""

import argparse
import numpy as np
import pandas as pd
import fastf1


CACHE_DIR = "./fastf1_cache"

# Rough real-world constants (seconds)
PIT_STOP_LOSS_MEAN = 22.5      # total time lost pitting under green flag
PIT_STOP_LOSS_STD = 1.5         # variation in pit loss (driver, pit crew, etc.)
SAFETY_CAR_PIT_LOSS_MULTIPLIER = 0.35  # pitting under SC is much cheaper
SAFETY_CAR_PROB_PER_LAP = 0.03         # naive flat per-lap probability, refine later


def setup_cache(path: str = CACHE_DIR) -> None:
    import os
    os.makedirs(path, exist_ok=True)
    fastf1.Cache.enable_cache(path)


def load_driver_laps(year: int, event: str, driver: str) -> pd.DataFrame:
    session = fastf1.get_session(year, event, "R")
    session.load(laps=True, telemetry=False, weather=False)
    laps = session.laps.pick_drivers(driver).pick_accurate()
    laps = laps[laps["FastF1Generated"] != True]
    laps = laps.copy()
    laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()
    return laps


def fit_naive_degradation_model(laps: pd.DataFrame) -> dict:
    """
    Fit lap_time = base_time + slope * tyre_life, per stint, then average
    the slope across stints (weighted by stint length).
    """
    stint_fits = []
    for stint_id, stint_laps in laps.groupby("Stint"):
        stint_laps = stint_laps.dropna(subset=["LapTimeSeconds", "TyreLife"])
        if len(stint_laps) < 4:
            continue
        x = stint_laps["TyreLife"].values.astype(float)
        y = stint_laps["LapTimeSeconds"].values.astype(float)
        slope, intercept = np.polyfit(x, y, 1)
        stint_fits.append({"stint": stint_id, "slope": slope, "intercept": intercept,
                            "n_laps": len(stint_laps)})

    if not stint_fits:
        raise ValueError("Not enough clean stint data to fit a degradation model. "
                          "Try a different driver or race.")

    fits_df = pd.DataFrame(stint_fits)
    weighted_slope = np.average(fits_df["slope"], weights=fits_df["n_laps"])
    weighted_intercept = np.average(fits_df["intercept"], weights=fits_df["n_laps"])
    slope_std = fits_df["slope"].std() if len(fits_df) > 1 else abs(weighted_slope) * 0.3

    return {
        "base_lap_time": weighted_intercept,
        "deg_slope": weighted_slope,
        "deg_slope_std": slope_std,
        "stint_fits": fits_df,
    }


def generate_common_random_numbers(model: dict, remaining_laps: int, n_trials: int,
                                    rng: np.random.Generator) -> dict:
    """
    Draw all randomness ONCE, shared across every strategy being compared.
    This is what makes trial i comparable across strategies.
    """
    deg_slopes = rng.normal(model["deg_slope"], model["deg_slope_std"], size=n_trials)
    deg_slopes = np.maximum(deg_slopes, 0.0)  # degradation shouldn't make you faster
    pit_loss_green = rng.normal(PIT_STOP_LOSS_MEAN, PIT_STOP_LOSS_STD, size=n_trials)
    # per-lap, per-trial safety car flags for every remaining lap
    sc_lap_flags = rng.random((n_trials, remaining_laps)) < SAFETY_CAR_PROB_PER_LAP
    return {
        "deg_slopes": deg_slopes,
        "pit_loss_green": pit_loss_green,
        "sc_lap_flags": sc_lap_flags,
    }


def total_time_fixed_offset(base_lap_time: float, current_tyre_age: int, remaining_laps: int,
                             offset, deg_slopes: np.ndarray, pit_loss: np.ndarray) -> np.ndarray:
    """
    Closed-form total race time for pitting after `offset` more laps.
    `offset` can be a python int (same for all trials) or a numpy array
    (a different effective offset per trial, used by the reactive strategy).

    Derivation: with a linear degradation model, total added-degradation-time
    is deg_slope * (sum of tyre ages across all laps). Tyre age runs
    current_tyre_age .. current_tyre_age+offset-1 before the stop, then
    resets to 0 and runs 0 .. (remaining_laps-offset-1) after — both are
    arithmetic sequences with closed-form sums, so no per-lap loop is needed.
    """
    pre_terms = offset
    pre_sum_age = pre_terms * current_tyre_age + pre_terms * (pre_terms - 1) / 2
    post_terms = remaining_laps - offset
    post_sum_age = post_terms * (post_terms - 1) / 2
    sum_age = pre_sum_age + post_sum_age

    lap_time_total = remaining_laps * base_lap_time + deg_slopes * sum_age
    return lap_time_total + pit_loss


def simulate_sweep(model: dict, current_tyre_age: int, remaining_laps: int,
                    max_offset: int, crn: dict) -> dict:
    """Evaluate every fixed pit-lap offset from 0 to max_offset (inclusive)."""
    sweep_results = {}
    for offset in range(0, max_offset + 1):
        # green-flag cost unless a safety car happens to be active on this
        # exact lap (naive: only checks the pit lap itself, not the whole race)
        sc_on_pit_lap = crn["sc_lap_flags"][:, offset]
        pit_loss = np.where(sc_on_pit_lap,
                             crn["pit_loss_green"] * SAFETY_CAR_PIT_LOSS_MULTIPLIER,
                             crn["pit_loss_green"])
        totals = total_time_fixed_offset(
            model["base_lap_time"], current_tyre_age, remaining_laps,
            offset, crn["deg_slopes"], pit_loss,
        )
        sweep_results[offset] = totals
    return sweep_results


def simulate_reactive(model: dict, current_tyre_age: int, remaining_laps: int,
                       window: int, fallback_offset: int, crn: dict) -> np.ndarray:
    """
    Reactive strategy: watch the next `window` laps for a safety car. If one
    appears, pit immediately (cheap stop) on the first lap it's active. If
    none appears in the window, fall back to pitting at `fallback_offset`
    under green-flag conditions.
    """
    sc_window = crn["sc_lap_flags"][:, :window]
    found_sc = sc_window.any(axis=1)
    first_sc_lap = np.argmax(sc_window, axis=1)  # 0 if none found — masked out below

    effective_offset = np.where(found_sc, first_sc_lap, fallback_offset)
    pit_loss = np.where(found_sc,
                         crn["pit_loss_green"] * SAFETY_CAR_PIT_LOSS_MULTIPLIER,
                         crn["pit_loss_green"])

    return total_time_fixed_offset(
        model["base_lap_time"], current_tyre_age, remaining_laps,
        effective_offset, crn["deg_slopes"], pit_loss,
    )


def main():
    parser = argparse.ArgumentParser(description="F1RaceOps M1 spike: pit strategy Monte Carlo")
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--event", type=str, default="Bahrain")
    parser.add_argument("--driver", type=str, default="VER", help="Three-letter driver code")
    parser.add_argument("--current-lap", type=int, default=20)
    parser.add_argument("--current-tyre-age", type=int, default=15)
    parser.add_argument("--race-total-laps", type=int, default=57)
    parser.add_argument("--n-trials", type=int, default=5000)
    parser.add_argument("--sweep-max-offset", type=int, default=20,
                         help="Sweep fixed pit-lap offsets from 0 to this value")
    parser.add_argument("--reactive-window", type=int, default=8,
                         help="Laps to watch for an opportunistic SC pit")
    parser.add_argument("--reactive-fallback-offset", type=int, default=None,
                         help="Offset to fall back to if no SC in window "
                              "(default: sweep-max-offset // 2)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)

    print(f"Loading {args.year} {args.event} laps for {args.driver}...")
    setup_cache()
    laps = load_driver_laps(args.year, args.event, args.driver)
    print(f"  {len(laps)} clean laps loaded.")

    print("Fitting naive per-stint degradation model...")
    model = fit_naive_degradation_model(laps)
    print(f"  base_lap_time ~= {model['base_lap_time']:.2f}s, "
          f"deg_slope ~= {model['deg_slope']:.3f}s/lap "
          f"(+/- {model['deg_slope_std']:.3f})")

    remaining_laps = args.race_total_laps - args.current_lap
    if remaining_laps < 1:
        parser.error(
            f"--current-lap ({args.current_lap}) must be less than "
            f"--race-total-laps ({args.race_total_laps}) — no laps remain to strategize over."
        )

    sweep_max = min(args.sweep_max_offset, remaining_laps - 1)
    # reactive_window is a slice bound (crn["sc_lap_flags"][:, :window]), so it
    # may validly be as large as remaining_laps itself — unlike sweep offsets,
    # which are used as direct column indices and must stay under remaining_laps.
    # Floor at 1 so a single remaining lap still gives a non-empty window.
    reactive_window = max(1, min(args.reactive_window, remaining_laps))
    reactive_fallback = args.reactive_fallback_offset
    if reactive_fallback is None:
        reactive_fallback = sweep_max // 2
    reactive_fallback = min(reactive_fallback, remaining_laps - 1)

    print(f"\nSimulating {args.n_trials} trials from lap {args.current_lap} "
          f"(tyre age {args.current_tyre_age}, {remaining_laps} laps remaining)...")
    print(f"  Sweeping fixed offsets 0..{sweep_max}, reactive window={reactive_window}, "
          f"reactive fallback offset={reactive_fallback}\n")

    crn = generate_common_random_numbers(model, remaining_laps, args.n_trials, rng)

    sweep_results = simulate_sweep(model, args.current_tyre_age, remaining_laps, sweep_max, crn)
    reactive_totals = simulate_reactive(model, args.current_tyre_age, remaining_laps,
                                         reactive_window, reactive_fallback, crn)

    print("=" * 66)
    print("FULL SWEEP (fixed offsets — cost curve)")
    print("=" * 66)
    sweep_means = {o: totals.mean() for o, totals in sweep_results.items()}
    for offset, totals in sweep_results.items():
        print(f"+{offset:<9}{totals.mean():>13.2f}s")

    best_fixed_offset = min(sweep_means, key=sweep_means.get)
    best_fixed_totals = sweep_results[best_fixed_offset]

    # Head-to-head comparison: Reactive vs. the single best fixed strategy.
    # Comparing reactive against ALL sweep offsets at once is confounded —
    # when the reactive strategy's SC-triggered offset matches a swept
    # offset on the same trial, both compute the exact same total (same
    # offset, same discount), and argmin's tie-breaking silently favors
    # whichever column comes first. A clean two-way comparison avoids that.
    head_to_head = np.column_stack([best_fixed_totals, reactive_totals])
    h2h_best_idx = np.argmin(head_to_head, axis=1)
    h2h_win_counts = np.bincount(h2h_best_idx, minlength=2)
    h2h_win_probs = h2h_win_counts / args.n_trials
    ties = int(np.sum(best_fixed_totals == reactive_totals))

    print("\n" + "=" * 66)
    print(f"Best fixed strategy: Pit +{best_fixed_offset} "
          f"(mean {best_fixed_totals.mean():.2f}s)")
    print(f"Reactive strategy:   window={reactive_window}, fallback=+{reactive_fallback} "
          f"(mean {reactive_totals.mean():.2f}s)")
    print("-" * 66)
    print("HEAD-TO-HEAD: Best Fixed vs. Reactive")
    print(f"  Best Fixed (+{best_fixed_offset}) wins: {h2h_win_probs[0]:.1%}")
    print(f"  Reactive wins:                    {h2h_win_probs[1]:.1%}")
    print(f"  Exact ties (same offset triggered, no real difference): "
          f"{ties / args.n_trials:.1%}")
    print(f"  Reactive P10={np.percentile(reactive_totals, 10):.2f}s, "
          f"P90={np.percentile(reactive_totals, 90):.2f}s")
    print("=" * 66)


if __name__ == "__main__":
    main()