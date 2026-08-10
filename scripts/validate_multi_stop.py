"""
F1RaceOps — validate the multi-stop Monte Carlo engine against real data.

Two checks:
  1. n_stops=1 via the NEW find_best_fixed_multi_stop/simulate_multi_stop
     should find the SAME best offset as the existing, already-validated
     run_monte_carlo.py path (simulate_sweep) — confirms the new code
     didn't introduce a regression for the default case.
  2. n_stops=2 (or more) runs and produces a sane, inspectable result.

Usage:
    python scripts/validate_multi_stop.py --race-id 1 --driver VER \
        --current-lap 20 --current-tyre-age 15 --compound MEDIUM --n-stops 2
"""

import argparse
import sys

sys.path.insert(0, ".")

import numpy as np
from sqlalchemy import select

from backend.database import get_session
from backend.models import Circuit, Driver, Race
from backend.simulation.lap_time_model import LapTimePredictor
from backend.simulation.monte_carlo import (
    find_best_fixed_multi_stop,
    simulate_multi_stop,
    simulate_sweep,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--race-id", type=int, required=True)
    parser.add_argument("--driver", type=str, required=True)
    parser.add_argument("--current-lap", type=int, required=True)
    parser.add_argument("--current-tyre-age", type=int, required=True)
    parser.add_argument("--compound", type=str, default="MEDIUM")
    parser.add_argument("--n-stops", type=int, default=2)
    parser.add_argument("--n-trials", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    db = get_session()
    try:
        race = db.get(Race, args.race_id)
        driver = db.execute(select(Driver).where(Driver.code == args.driver.upper())).scalars().first()
        circuit = db.get(Circuit, race.circuit_id)
        predictor = LapTimePredictor(db)
        base = predictor.estimate_base_pace(race.id, driver.id, race.total_laps)
        pit_loss_model = predictor.get_pit_loss(circuit.circuit_ref)

        print(f"Base pace: {base.base_pace_seconds:.2f}s | Pit loss: {pit_loss_model.mean_seconds:.2f}s "
              f"| Deg slope ({args.compound}): {predictor.get_degradation_slope(args.compound):.4f}s/lap\n")

        # --- Check 1: n_stops=1 should match the existing validated path ---
        print("=" * 60)
        print("CHECK 1: n_stops=1 vs. existing simulate_sweep")
        print("=" * 60)
        rng = np.random.default_rng(args.seed)
        remaining_laps = race.total_laps - args.current_lap
        sweep_results, _ = simulate_sweep(
            predictor, pit_loss_model, base.base_pace_seconds, args.compound,
            args.current_tyre_age, args.current_lap, race.total_laps,
            max_offset=min(30, remaining_laps - 1), n_trials=args.n_trials, rng=rng,
        )
        sweep_means = {o: t.mean() for o, t in sweep_results.items()}
        old_best = min(sweep_means, key=sweep_means.get)
        print(f"Existing simulate_sweep best offset: +{old_best} (mean {sweep_means[old_best]:.2f}s)")

        new_offsets, new_compounds, new_cost = find_best_fixed_multi_stop(
            predictor, pit_loss_model, base.base_pace_seconds, args.compound,
            args.current_tyre_age, args.current_lap, race.total_laps, n_stops=1,
        )
        print(f"New find_best_fixed_multi_stop(n_stops=1): offsets={new_offsets}, "
              f"compounds={new_compounds} (deterministic cost {new_cost:.2f}s)")
        match = "MATCH" if new_offsets[0] == old_best else "MISMATCH -- investigate before trusting n_stops>1"
        print(f"--> {match}\n")

        # --- Check 2: the actual n_stops requested ---
        print("=" * 60)
        print(f"CHECK 2: n_stops={args.n_stops}")
        print("=" * 60)
        best_offsets, best_compounds, best_cost = find_best_fixed_multi_stop(
            predictor, pit_loss_model, base.base_pace_seconds, args.compound,
            args.current_tyre_age, args.current_lap, race.total_laps, n_stops=args.n_stops,
        )
        print(f"Best {args.n_stops}-stop offsets (relative to lap {args.current_lap}): {best_offsets}")
        print(f"  -> absolute pit laps: {[args.current_lap + o for o in best_offsets]}")
        print(f"  -> stint compounds: {best_compounds}")
        print(f"Deterministic cost estimate: {best_cost:.2f}s")

        rng2 = np.random.default_rng(args.seed + 1)
        totals = simulate_multi_stop(
            predictor, pit_loss_model, base.base_pace_seconds,
            args.current_tyre_age, args.current_lap, race.total_laps,
            best_offsets, best_compounds, args.n_trials, rng2,
        )
        print(f"Monte Carlo mean: {totals.mean():.2f}s | P10: {np.percentile(totals,10):.2f}s "
              f"| P90: {np.percentile(totals,90):.2f}s")

        print(f"\nComparison: 1-stop best was {sweep_means[old_best]:.2f}s, "
              f"{args.n_stops}-stop best is {totals.mean():.2f}s "
              f"({'better' if totals.mean() < sweep_means[old_best] else 'worse'} for this scenario)")

    finally:
        db.close()


if __name__ == "__main__":
    main()