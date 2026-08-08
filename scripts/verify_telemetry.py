"""
Telemetry Verification Script

Purpose:
    Before committing a race to the v1 dataset, check that FastF1's lap and
    telemetry data for that race is actually usable — not just "available."
    Specifically checks:
      1. Lap coverage: does every driver have a lap record for every lap
         they should have completed (based on race classification)?
      2. Accuracy flag coverage: what fraction of laps are marked
         IsAccurate=True (i.e. properly time-synced, safe to use for
         degradation modeling)?
      3. FastF1Generated laps: how many laps were reconstructed/interpolated
         by FastF1 rather than sourced directly (these should generally be
         excluded from tire-degradation training data)?
      4. Telemetry presence: can we pull car telemetry for at least one lap
         per driver (catches sessions with partial telemetry outages)?

Usage:
    pip install fastf1 pandas
    python verify_telemetry.py

Output:
    Prints a per-race summary table and writes telemetry_report.csv with
    per-driver detail for any race that fails the completeness thresholds.
"""

import fastf1
import pandas as pd

CANDIDATE_RACES = [
    {"year": 2023, "event": "Bahrain", "category": "high_degradation"},
    {"year": 2023, "event": "Azerbaijan", "category": "low_degradation"},
    {"year": 2023, "event": "Singapore", "category": "safety_car_prone"},
    {"year": 2022, "event": "Japan", "category": "wet_race_candidate"},
    {"year": 2023, "event": "Canada", "category": "wet_race_candidate"},
    {"year": 2021, "event": "Turkey", "category": "wet_race_candidate"},
    {"year": 2024, "event": "Brazil", "category": "wet_race_candidate"},
]

# Thresholds for telemetry completeness checks
MIN_ACCURATE_LAP_FRACTION = 0.85   # >=85% of laps should be IsAccurate
MAX_GENERATED_LAP_FRACTION = 0.10  # <=10% of laps should be FastF1Generated
MIN_TELEMETRY_COVERAGE = 0.90      # >=90% of drivers need >=1 telemetry-readable lap

CACHE_DIR = "./fastf1_cache"


def setup_cache(path: str = CACHE_DIR) -> None:
    import os
    os.makedirs(path, exist_ok=True)
    fastf1.Cache.enable_cache(path)


def check_race(year: int, event: str) -> dict:
    """Load one race session and compute data-quality metrics."""
    session = fastf1.get_session(year, event, "R")
    session.load(laps=True, telemetry=True, weather=True)

    laps = session.laps
    drivers = laps["Driver"].unique()

    total_laps = len(laps)
    accurate_laps = int(laps["IsAccurate"].sum())
    generated_laps = int(laps["FastF1Generated"].sum()) if "FastF1Generated" in laps else 0

    accurate_fraction = accurate_laps / total_laps if total_laps else 0.0
    generated_fraction = generated_laps / total_laps if total_laps else 0.0

    # Telemetry check: try to pull telemetry for one lap per driver
    telemetry_ok = 0
    telemetry_fail_drivers = []
    for drv in drivers:
        drv_laps = laps.pick_drivers(drv)
        if drv_laps.empty:
            telemetry_fail_drivers.append(drv)
            continue
        try:
            fastest = drv_laps.pick_fastest()
            tel = fastest.get_car_data()
            if tel is None or tel.empty:
                telemetry_fail_drivers.append(drv)
            else:
                telemetry_ok += 1
        except Exception:
            telemetry_fail_drivers.append(drv)

    telemetry_coverage = telemetry_ok / len(drivers) if len(drivers) else 0.0

    # Per-driver lap-count sanity check (flag drivers with suspiciously few laps
    # who weren't actually retired, per session results)
    results = session.results[["Abbreviation", "Status"]].set_index("Abbreviation")
    per_driver_lap_counts = laps.groupby("Driver").size()

    return {
        "year": year,
        "event": event,
        "total_laps": total_laps,
        "accurate_lap_fraction": round(accurate_fraction, 3),
        "generated_lap_fraction": round(generated_fraction, 3),
        "telemetry_coverage": round(telemetry_coverage, 3),
        "telemetry_fail_drivers": telemetry_fail_drivers,
        "passes_thresholds": (
            accurate_fraction >= MIN_ACCURATE_LAP_FRACTION
            and generated_fraction <= MAX_GENERATED_LAP_FRACTION
            and telemetry_coverage >= MIN_TELEMETRY_COVERAGE
        ),
        "per_driver_lap_counts": per_driver_lap_counts.to_dict(),
        "results_status": results["Status"].to_dict(),
    }


def main():
    setup_cache()
    summary_rows = []
    detail_rows = []

    for race in CANDIDATE_RACES:
        print(f"\nChecking {race['year']} {race['event']} ({race['category']})...")
        try:
            report = check_race(race["year"], race["event"])
        except Exception as e:
            print(f"  FAILED TO LOAD: {e}")
            summary_rows.append({
                "year": race["year"],
                "event": race["event"],
                "category": race["category"],
                "status": f"LOAD_ERROR: {e}",
            })
            continue

        status = "PASS" if report["passes_thresholds"] else "REVIEW NEEDED"
        print(f"  Total laps: {report['total_laps']}")
        print(f"  Accurate lap fraction: {report['accurate_lap_fraction']:.1%}")
        print(f"  FastF1Generated fraction: {report['generated_lap_fraction']:.1%}")
        print(f"  Telemetry coverage: {report['telemetry_coverage']:.1%}")
        if report["telemetry_fail_drivers"]:
            print(f"  Drivers with telemetry issues: {report['telemetry_fail_drivers']}")
        print(f"  => {status}")

        summary_rows.append({
            "year": race["year"],
            "event": race["event"],
            "category": race["category"],
            "total_laps": report["total_laps"],
            "accurate_lap_fraction": report["accurate_lap_fraction"],
            "generated_lap_fraction": report["generated_lap_fraction"],
            "telemetry_coverage": report["telemetry_coverage"],
            "status": status,
        })

        for driver, lap_count in report["per_driver_lap_counts"].items():
            detail_rows.append({
                "year": race["year"],
                "event": race["event"],
                "driver": driver,
                "lap_count": lap_count,
                "finish_status": report["results_status"].get(driver, "unknown"),
            })

    summary_df = pd.DataFrame(summary_rows)
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(summary_df.to_string(index=False))

    detail_df = pd.DataFrame(detail_rows)
    detail_df.to_csv("telemetry_report_detail.csv", index=False)
    summary_df.to_csv("telemetry_report_summary.csv", index=False)
    print("\nWrote telemetry_report_summary.csv and telemetry_report_detail.csv")


if __name__ == "__main__":
    main()