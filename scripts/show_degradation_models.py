"""
F1RaceOps — print fitted per-compound degradation models, plus a diagnostic
breakdown of how many laps survive each filtering stage per compound (useful
for understanding why a compound might have no fitted model at all).

Usage:
    python scripts/show_degradation_models.py
"""

import sys

sys.path.insert(0, ".")

from backend.database import get_session
from backend.simulation.tire_models.deterministic import (
    fit_degradation_models,
    get_compound_lap_diagnostics,
)


def main():
    db = get_session()
    try:
        diagnostics = get_compound_lap_diagnostics(db)
        models = fit_degradation_models(db)
    finally:
        db.close()

    print("=" * 70)
    print("LAP COUNT DIAGNOSTICS (per compound, by filtering stage)")
    print("=" * 70)
    print(f"{'Compound':<15}{'Total Laps':>12}{'Accurate+Clean':>16}{'After In/Out Excl.':>20}")
    for compound in sorted(diagnostics, key=lambda c: -diagnostics[c]['total_laps']):
        d = diagnostics[compound]
        print(f"{compound:<15}{d['total_laps']:>12}{d['accurate_clean_laps']:>16}{d['after_inout_exclusion']:>20}")

    print("\n" + "=" * 70)
    print("FITTED DEGRADATION MODELS (tyre-age effect, fuel-burn effect controlled for)")
    print("=" * 70)
    if not models:
        print("No degradation models could be fit — check that races have been ingested.")
        return

    print(f"{'Compound':<15}{'Deg Slope':>12}{'(SE)':>10}{'Fuel Slope':>13}{'(SE)':>10}{'Stints':>9}{'Laps':>7}")
    for compound in sorted(models, key=lambda c: models[c].deg_slope):
        m = models[compound]
        print(f"{m.compound:<15}{m.deg_slope:>12.4f}{m.deg_slope_se:>10.4f}"
              f"{m.fuel_slope:>13.4f}{m.fuel_slope_se:>10.4f}{m.n_stints:>9}{m.n_laps:>7}")

    print("\nNote: compounds present in diagnostics but absent from the fitted")
    print("models table didn't meet the minimum stint/lap thresholds needed to")
    print("reliably separate tyre-age effect from fuel-burn effect.")


if __name__ == "__main__":
    main()