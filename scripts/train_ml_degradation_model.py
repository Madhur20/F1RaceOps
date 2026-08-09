"""
F1RaceOps — train and evaluate the ML tire degradation model.

Usage:
    python scripts/train_ml_degradation_model.py
"""

import sys

sys.path.insert(0, ".")

from backend.database import get_session
from backend.simulation.tire_models.ml_model import build_lap_dataset, train_and_evaluate


def main():
    db = get_session()
    try:
        df = build_lap_dataset(db)
    finally:
        db.close()

    print(f"Loaded {len(df)} clean laps across {df['stint_key'].nunique()} stints, "
          f"{df['circuit_ref'].nunique()} circuits, {df['driver_code'].nunique()} drivers.\n")

    result = train_and_evaluate(df)

    print("=" * 60)
    print("ML MODEL — STINT-LEVEL HELD-OUT EVALUATION")
    print("=" * 60)
    print(f"Train: {result.n_train_laps} laps across {result.n_train_stints} stints")
    print(f"Test:  {result.n_test_laps} laps across {result.n_test_stints} stints (held out)")
    print(f"\nMean absolute error:   {result.mae:.3f}s")
    print(f"Median absolute error: {result.median_ae:.3f}s")
    print(f"90th percentile error: {result.p90_ae:.3f}s")

    print("\n" + "=" * 60)
    print("TOP FEATURE IMPORTANCES")
    print("=" * 60)
    for name, importance in result.feature_importances.items():
        print(f"{name:<30}{importance:.4f}")

    print("\nNote: this MAE uses a different evaluation protocol than the")
    print("deterministic model's Step 4 validation (0.826s) — see the module")
    print("docstring in backend/simulation/tire_models/ml_model.py before")
    print("comparing the two numbers directly.")


if __name__ == "__main__":
    main()