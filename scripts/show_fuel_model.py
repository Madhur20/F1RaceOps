"""
F1RaceOps — print the fuel-effect model's curve across a sample race.

Usage:
    python scripts/show_fuel_model.py
"""

import sys

sys.path.insert(0, ".")

from backend.simulation.fuel_model import estimate_fuel_effect


def main():
    total_laps = 57  # e.g. Bahrain
    print(f"Fuel effect model — {total_laps}-lap race, {110.0} kg starting fuel, 0.03 s/kg\n")
    print(f"{'Lap':<6}{'Fuel Remaining (kg)':>22}{'Lap Time Delta (s)':>22}")
    for lap in [1, 5, 10, 20, 30, 40, 50, 57]:
        est = estimate_fuel_effect(lap, total_laps)
        print(f"{est.lap_number:<6}{est.fuel_remaining_kg:>22.1f}{est.lap_time_delta_seconds:>22.3f}")


if __name__ == "__main__":
    main()