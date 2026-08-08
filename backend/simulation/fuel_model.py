"""
F1RaceOps — fuel-effect model.

UNLIKE the degradation model (backend/simulation/tire_models/deterministic.py)
and the pit-loss model (backend/simulation/pit_loss_model.py), this is NOT
fit from real telemetry — FastF1 does not expose fuel load data at all (the
same gap noted in M3's race state engine). This is a standard, publicly
documented physics approximation instead:

  - Fuel effect: ~0.03 seconds per kg of fuel carried, per lap. Commonly
    cited range across F1 technical sources is roughly 0.025-0.04 s/kg;
    0.03 is used here as a reasonable point estimate, not derived from
    this project's own data.
  - Starting fuel load: 110 kg, the current FIA maximum race fuel mass.
  - Burn rate: assumed LINEAR across the race (fuel depletes evenly lap to
    lap) — a simplification. Real consumption varies somewhat by circuit
    and driving style, but linear is the standard first-order assumption
    and is what M3's placeholder fuel estimate already used.

Because this is an approximation rather than a fitted model, it has no
standard error or confidence interval the way the other two models do —
that distinction is intentional and should stay visible wherever this
model's output is used (e.g. don't present its lap-time contribution with
the same certainty as the measured degradation/pit-loss numbers).
"""

from dataclasses import dataclass

FUEL_EFFECT_SECONDS_PER_KG = 0.03   # see module docstring for sourcing
STARTING_FUEL_KG = 110.0            # current FIA max race fuel mass


@dataclass
class FuelEffectEstimate:
    lap_number: int
    total_laps: int
    fuel_remaining_kg: float
    # Seconds ADDED to a zero-fuel baseline lap time by the fuel still on
    # board at this lap. Always >= 0; decreases toward 0 as the race
    # progresses and fuel burns off.
    lap_time_delta_seconds: float


def estimate_fuel_effect(lap_number: int, total_laps: int) -> FuelEffectEstimate:
    """
    Linear depletion: full tank (110 kg) at lap 1, empty at the final lap.
    Returns the estimated lap-time cost of the fuel still on board.
    """
    if total_laps <= 0:
        raise ValueError("total_laps must be positive")
    lap_number = max(1, min(lap_number, total_laps))

    fraction_remaining = 1.0 - (lap_number - 1) / total_laps
    fuel_remaining_kg = max(0.0, fraction_remaining * STARTING_FUEL_KG)
    lap_time_delta = fuel_remaining_kg * FUEL_EFFECT_SECONDS_PER_KG

    return FuelEffectEstimate(
        lap_number=lap_number,
        total_laps=total_laps,
        fuel_remaining_kg=round(fuel_remaining_kg, 2),
        lap_time_delta_seconds=round(lap_time_delta, 3),
    )


def total_fuel_effect_over_stint(start_lap: int, end_lap: int, total_laps: int) -> float:
    """
    Sum of the fuel-effect lap-time delta across a range of laps (start_lap
    to end_lap inclusive) — useful for comparing total fuel cost across
    candidate stint lengths in the combined lap-time model (Step 4).
    """
    return sum(
        estimate_fuel_effect(lap, total_laps).lap_time_delta_seconds
        for lap in range(start_lap, end_lap + 1)
    )