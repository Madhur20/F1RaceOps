"""
F1RaceOps — ingest the finalized v1 race set.

Usage:
    python scripts/ingest_all_races.py

Run from the repo root with the venv active. Safe to re-run: each race's
existing rows are cleared and replaced (see _clear_existing_race_data in
backend/ingestion/load_race.py), rather than duplicated.
"""

import logging
import sys

sys.path.insert(0, ".")  # repo root, so `backend` is importable when run as a script

from backend.ingestion.load_race import load_race

logging.basicConfig(level=logging.INFO, format="%(levelname)-5s %(message)s")

# The finalized v1 set — see docs/phase0-plan.md section 6.
V1_RACES = [
    (2023, "Bahrain"),      # high degradation
    (2023, "Azerbaijan"),   # low degradation
    (2023, "Singapore"),    # safety-car-prone
    (2021, "Turkey"),       # wet
    (2023, "Canada"),       # mixed/wet
]


def main():
    failures = []
    for year, event in V1_RACES:
        try:
            load_race(year, event)
        except Exception as e:
            logging.exception("Failed to load %s %s", year, event)
            failures.append((year, event, str(e)))

    print("\n" + "=" * 50)
    if failures:
        print(f"{len(V1_RACES) - len(failures)}/{len(V1_RACES)} races loaded successfully.")
        print("Failures:")
        for year, event, err in failures:
            print(f"  {year} {event}: {err}")
        sys.exit(1)
    else:
        print(f"All {len(V1_RACES)} races loaded successfully.")


if __name__ == "__main__":
    main()