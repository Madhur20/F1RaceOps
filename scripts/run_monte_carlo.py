"""
F1RaceOps — Monte Carlo strategy comparison using REAL validated models
(M4's degradation/pit-loss/fuel models), replacing the M1 spike's naive
single-race degradation fit and placeholder pit-loss constant.

Usage:
    python scripts/run_monte_carlo.py --race-id 1 --driver VER --current-lap 20 --current-tyre-age 15
"""

import argparse
import sys

sys.path.insert(0, ".")

import numpy as np
from sqlalchemy import select

from backend.database import get_session
from backend.models import Circuit, Driver, Race
from backend.simulation.lap_time_model import LapTimePredictor
from backend.simulation.monte_carlo import simulate_reactive, simulate_sweep


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--race-id", type=int, required=True)
    parser.add_argument("--driver", type=str, required=True, help="Driver code, e.g. VER")
    parser.add_argument("--current-lap", type=int, required=True)
    parser.add_argument("--current-tyre-age", type=int, required=True)
    parser.add_argument("--compound", type=str, default="MEDIUM")
    parser.add_argument("--n-trials", type=int, default=5000)
    parser.add_argument("--sweep-max-offset", type=int, default=20)
    parser.add_argument("--reactive-window", type=int, default=8)
    parser.add_argument("--reactive-fallback-offset", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    db = get_session()
    try:
        race = db.get(Race, args.race_id)
        if race is None or race.total_laps is None:
            print(f"Race {args.race_id} not found or missing total_laps.")
            return
        driver = db.execute(select(Driver).where(Driver.code == args.driver.upper())).scalars().first()
        if driver is None:
            print(f"Driver {args.driver} not found.")
            return
        circuit = db.get(Circuit, race.circuit_id)

        print("Loading validated models (degradation, pit-loss, fuel)...")
        predictor = LapTimePredictor(db)

        base = predictor.estimate_base_pace(race.id, driver.id, race.total_laps)
        if base is None:
            print(f"Could not estimate base pace for {args.driver} in this race "
                  f"(not enough clean early laps).")
            return
        print(f"Base pace for {args.driver}: {base.base_pace_seconds:.2f}s "
              f"(from {base.n_laps_used} early laps, std={base.std_seconds:.2f})")

        pit_loss_model = predictor.get_pit_loss(circuit.circuit_ref)
        print(f"Pit-loss model for {circuit.name}: {pit_loss_model.mean_seconds:.2f}s "
              f"+/- {pit_loss_model.std_seconds:.2f}s (n={pit_loss_model.n_stops})")

        deg_slope = predictor.get_degradation_slope(args.compound)
        print(f"Degradation slope for {args.compound}: {deg_slope:.4f}s/lap\n")

        remaining_laps = race.total_laps - args.current_lap
        sweep_max = min(args.sweep_max_offset, remaining_laps - 1)
        reactive_window = max(1, min(args.reactive_window, remaining_laps))
        reactive_fallback = args.reactive_fallback_offset
        if reactive_fallback is None:
            reactive_fallback = sweep_max // 2
        reactive_fallback = min(reactive_fallback, remaining_laps - 1)

        print(f"Simulating {args.n_trials} trials from lap {args.current_lap} "
              f"(tyre age {args.current_tyre_age}, {remaining_laps} laps remaining)...")
        print(f"Sweeping offsets 0..{sweep_max}, reactive window={reactive_window}, "
              f"fallback=+{reactive_fallback}\n")

        sweep_results, crn = simulate_sweep(
            predictor, pit_loss_model, base.base_pace_seconds, args.compound,
            args.current_tyre_age, args.current_lap, race.total_laps,
            sweep_max, args.n_trials, rng,
        )
        reactive_totals = simulate_reactive(
            predictor, pit_loss_model, base.base_pace_seconds, args.compound,
            args.current_tyre_age, args.current_lap, race.total_laps,
            reactive_window, reactive_fallback, args.n_trials, crn,
        )

        print("=" * 60)
        print("SWEEP (fixed offsets)")
        print("=" * 60)
        sweep_means = {o: totals.mean() for o, totals in sweep_results.items()}
        for offset, totals in sweep_results.items():
            print(f"+{offset:<9}{totals.mean():>12.2f}s")

        best_fixed_offset = min(sweep_means, key=sweep_means.get)
        best_fixed_totals = sweep_results[best_fixed_offset]

        head_to_head = np.column_stack([best_fixed_totals, reactive_totals])
        h2h_win_idx = np.argmin(head_to_head, axis=1)
        h2h_win_probs = np.bincount(h2h_win_idx, minlength=2) / args.n_trials
        ties = int(np.sum(best_fixed_totals == reactive_totals))

        print("\n" + "=" * 60)
        print(f"Best fixed strategy: Pit +{best_fixed_offset} (mean {best_fixed_totals.mean():.2f}s)")
        print(f"Reactive strategy: window={reactive_window}, fallback=+{reactive_fallback} "
              f"(mean {reactive_totals.mean():.2f}s)")
        print("-" * 60)
        print(f"Best Fixed wins: {h2h_win_probs[0]:.1%}")
        print(f"Reactive wins:   {h2h_win_probs[1]:.1%}")
        print(f"Ties:            {ties / args.n_trials:.1%}")
        print("=" * 60)

    finally:
        db.close()


if __name__ == "__main__":
    main()