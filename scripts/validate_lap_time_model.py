"""
F1RaceOps — validate the combined lap-time model against real, held-out data.

Base pace is estimated from each driver's EARLY laps only (low tyre_age).
This script then predicts lap times for their LATER laps (never used to fit
anything) and compares against what actually happened — the real test of
whether Steps 1-4 combine into something trustworthy, not just "does it run."

Usage:
    python scripts/validate_lap_time_model.py
"""

import sys

sys.path.insert(0, ".")

import numpy as np
from sqlalchemy import select

from backend.database import get_session
from backend.models import Driver, Lap, Race
from backend.simulation.lap_time_model import LapTimePredictor
from backend.simulation.tire_models.deterministic import get_excluded_lap_keys


def main():
    db = get_session()
    try:
        predictor = LapTimePredictor(db)
        in_lap_keys, out_lap_keys = get_excluded_lap_keys(db)

        races = db.execute(select(Race)).scalars().all()
        all_errors = []

        print(f"{'Race':<20}{'Driver':<8}{'Base Pace':>11}{'Laps Tested':>13}{'Mean Abs Err (s)':>19}")

        for race in races:
            if race.total_laps is None:
                continue
            drivers = db.execute(
                select(Driver.id, Driver.code)
                .join(Lap, Lap.driver_id == Driver.id)
                .where(Lap.race_id == race.id)
                .distinct()
            ).all()

            for driver_id, driver_code in drivers:
                base = predictor.estimate_base_pace(race.id, driver_id, race.total_laps)
                if base is None:
                    continue

                # test laps: everything with tyre_age > max_base_pace_tyre_age,
                # i.e. NOT used to estimate base pace — genuine held-out data
                stmt = select(Lap.lap_number, Lap.lap_time_ms, Lap.tyre_life, Lap.compound).where(
                    Lap.race_id == race.id, Lap.driver_id == driver_id,
                    Lap.is_accurate.is_(True), Lap.is_generated.is_(False),
                    Lap.lap_time_ms.is_not(None), Lap.tyre_life.is_not(None),
                    Lap.tyre_life > predictor.max_base_pace_tyre_age,
                )
                test_laps = db.execute(stmt).all()

                errors = []
                for lap_number, lap_time_ms, tyre_life, compound in test_laps:
                    key = (race.id, driver_id, lap_number)
                    if key in in_lap_keys or key in out_lap_keys or compound is None:
                        continue
                    actual = lap_time_ms / 1000
                    predicted = predictor.predict_lap_time(
                        base.base_pace_seconds, compound, tyre_life, lap_number, race.total_laps
                    )
                    errors.append(abs(actual - predicted))

                if len(errors) < 3:
                    continue
                mean_abs_err = float(np.mean(errors))
                all_errors.extend(errors)
                print(f"{race.name[:19]:<20}{driver_code:<8}{base.base_pace_seconds:>11.2f}"
                      f"{len(errors):>13}{mean_abs_err:>19.3f}")

        print("\n" + "=" * 75)
        if all_errors:
            print(f"Overall mean absolute error across all held-out laps: {np.mean(all_errors):.3f}s")
            print(f"Overall median absolute error: {np.median(all_errors):.3f}s")
            print(f"90th percentile absolute error: {np.percentile(all_errors, 90):.3f}s")
        print("=" * 75)

    finally:
        db.close()


if __name__ == "__main__":
    main()