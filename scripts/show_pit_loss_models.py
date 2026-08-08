"""
F1RaceOps — print fitted per-circuit pit-loss models.

Usage:
    python scripts/show_pit_loss_models.py
"""

import sys

sys.path.insert(0, ".")

from backend.database import get_session
from backend.simulation.pit_loss_model import fit_pit_loss_models, get_global_fallback_model


def main():
    db = get_session()
    try:
        models = fit_pit_loss_models(db)
        fallback = get_global_fallback_model(db)
    finally:
        db.close()

    print("=" * 75)
    print("PER-CIRCUIT PIT-LOSS MODELS")
    print("=" * 75)
    print(f"{'Circuit':<25}{'Mean (s)':>12}{'Std (s)':>10}{'Stops':>8}{'Outliers Excl.':>16}")
    for ref in sorted(models, key=lambda r: models[r].mean_seconds):
        m = models[ref]
        print(f"{m.circuit_name:<25}{m.mean_seconds:>12.2f}{m.std_seconds:>10.2f}"
              f"{m.n_stops:>8}{m.n_excluded_outliers:>16}")

    print("\n" + "-" * 75)
    print(f"{'Global fallback':<25}{fallback.mean_seconds:>12.2f}{fallback.std_seconds:>10.2f}"
          f"{fallback.n_stops:>8}{fallback.n_excluded_outliers:>16}")

    print("\nCompare against the M1 spike's placeholder: 22.5s +/- 1.5s for every circuit.")


if __name__ == "__main__":
    main()