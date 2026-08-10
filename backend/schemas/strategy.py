"""
F1RaceOps — schemas for POST /strategy/simulate.

Richer than the original Phase 0 API contract sketch (docs/phase0-plan.md),
which was written before M1-M5 existed and only asked for a few candidate
pit laps and win probabilities. This reflects what was actually built: a
full cost-curve sweep plus a safety-car-reactive strategy, evaluated with
common random numbers for a statistically valid head-to-head comparison.
"""

from pydantic import BaseModel, Field


class StrategySimulationRequest(BaseModel):
    race_id: int
    driver_code: str = Field(..., description="Three-letter driver code, e.g. VER")
    current_lap: int = Field(..., ge=1)
    current_tyre_age: int = Field(..., ge=0)
    compound: str = Field("MEDIUM", description="Current tyre compound (already on the car)")
    n_trials: int = Field(5000, ge=100, le=20000, description="Monte Carlo trial count")
    sweep_max_offset: int = Field(20, ge=1, description="Sweep fixed pit offsets 0..this value (n_remaining_stops=1 only)")
    reactive_window: int = Field(8, ge=1, description="Laps to watch for an opportunistic SC pit (n_remaining_stops=1 only)")
    reactive_fallback_offset: int | None = Field(
        None, description="Offset to fall back to if no SC in window (default: sweep_max_offset // 2)"
    )
    n_remaining_stops: int = Field(
        1, ge=1, le=3,
        description="How many more pit stops to plan for. 1 uses the sweep+reactive comparison; "
                     ">1 searches pit-lap AND per-stint compound combinations, capped at 3 to keep "
                     "the search space tractable.",
    )
    allowed_compounds: list[str] | None = Field(
        None,
        description="Compounds to consider for stints AFTER the current one (n_remaining_stops>1 only). "
                     "Defaults to every compound with a fitted degradation model.",
    )
    seed: int | None = Field(None, description="Optional seed for reproducible results; random if omitted")


class SweepPoint(BaseModel):
    offset: int
    mean_seconds: float


class ReactiveStrategyResult(BaseModel):
    window: int
    fallback_offset: int
    mean_seconds: float


class HeadToHeadResult(BaseModel):
    best_fixed_win_probability: float
    reactive_win_probability: float
    tie_probability: float


class MultiStopResult(BaseModel):
    n_stops: int
    pit_laps: list[int]  # absolute lap numbers, not offsets
    stint_compounds: list[str]  # length n_stops + 1; first entry is the current compound
    mean_seconds: float
    p10_seconds: float
    p90_seconds: float


class StrategySimulationResponse(BaseModel):
    race_id: int
    driver_code: str
    current_lap: int
    current_tyre_age: int
    compound: str
    n_trials: int
    n_remaining_stops: int

    base_pace_seconds: float
    base_pace_n_laps_used: int

    circuit_name: str
    pit_loss_mean_seconds: float
    pit_loss_std_seconds: float
    pit_loss_model_source: str  # "circuit-specific" or "global fallback"

    degradation_slope: float
    degradation_model_available: bool  # False if this compound had no fitted model (see deterministic.py)

    # Populated only when n_remaining_stops == 1:
    sweep: list[SweepPoint] | None = None
    best_fixed_offset: int | None = None
    best_fixed_mean_seconds: float | None = None
    reactive: ReactiveStrategyResult | None = None
    head_to_head: HeadToHeadResult | None = None

    # Populated only when n_remaining_stops > 1:
    multi_stop: MultiStopResult | None = None