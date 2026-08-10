"""
F1RaceOps — /strategy API router.

POST /strategy/simulate — the culmination of M1 (proved the Monte Carlo
mechanism works), M4 (validated degradation/pit-loss/fuel models), and
M6 Step 1 (wired them into the simulation core). This endpoint is that
core, exposed live.
"""

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Circuit, Driver, Race
from backend.schemas.strategy import (
    HeadToHeadResult,
    MultiStopResult,
    ReactiveStrategyResult,
    StrategySimulationRequest,
    StrategySimulationResponse,
    SweepPoint,
)
from backend.simulation.lap_time_model import LapTimePredictor
from backend.simulation.monte_carlo import (
    find_best_fixed_multi_stop,
    simulate_multi_stop,
    simulate_reactive,
    simulate_sweep,
)

router = APIRouter(prefix="/strategy", tags=["strategy"])


@router.post("/simulate", response_model=StrategySimulationResponse)
def simulate_strategy(request: StrategySimulationRequest, db: Session = Depends(get_db)):
    race = db.get(Race, request.race_id)
    if race is None:
        raise HTTPException(status_code=404, detail=f"Race {request.race_id} not found")
    if race.total_laps is None:
        raise HTTPException(status_code=400, detail=f"Race {request.race_id} has no total_laps recorded")
    if request.current_lap >= race.total_laps:
        raise HTTPException(
            status_code=400,
            detail=f"current_lap ({request.current_lap}) must be less than "
                    f"total_laps ({race.total_laps}) for this race",
        )

    driver = db.execute(
        select(Driver).where(Driver.code == request.driver_code.upper())
    ).scalars().first()
    if driver is None:
        raise HTTPException(status_code=404, detail=f"Driver {request.driver_code} not found")

    circuit = db.get(Circuit, race.circuit_id)

    predictor = LapTimePredictor(db)
    base = predictor.estimate_base_pace(race.id, driver.id, race.total_laps)
    if base is None:
        raise HTTPException(
            status_code=400,
            detail=f"Could not estimate base pace for {request.driver_code} in this race "
                    f"(not enough clean early laps).",
        )

    pit_loss_model = predictor.get_pit_loss(circuit.circuit_ref)
    pit_loss_source = (
        "circuit-specific" if circuit.circuit_ref in predictor.pit_loss_models else "global fallback"
    )

    degradation_model_available = request.compound in predictor.degradation_models
    deg_slope = predictor.get_degradation_slope(request.compound)

    remaining_laps = race.total_laps - request.current_lap

    rng = np.random.default_rng(request.seed)  # None seed -> nondeterministic, as documented

    if request.n_remaining_stops == 1:
        # --- Unchanged from before n_remaining_stops existed ---
        sweep_max = min(request.sweep_max_offset, remaining_laps - 1)
        reactive_window = max(1, min(request.reactive_window, remaining_laps))
        reactive_fallback = request.reactive_fallback_offset
        if reactive_fallback is None:
            reactive_fallback = sweep_max // 2
        reactive_fallback = min(reactive_fallback, remaining_laps - 1)

        sweep_results, crn = simulate_sweep(
            predictor, pit_loss_model, base.base_pace_seconds, request.compound,
            request.current_tyre_age, request.current_lap, race.total_laps,
            sweep_max, request.n_trials, rng,
        )
        reactive_totals = simulate_reactive(
            predictor, pit_loss_model, base.base_pace_seconds, request.compound,
            request.current_tyre_age, request.current_lap, race.total_laps,
            reactive_window, reactive_fallback, request.n_trials, crn,
        )

        sweep_means = {o: float(totals.mean()) for o, totals in sweep_results.items()}
        best_fixed_offset = min(sweep_means, key=sweep_means.get)
        best_fixed_totals = sweep_results[best_fixed_offset]

        head_to_head = np.column_stack([best_fixed_totals, reactive_totals])
        win_idx = np.argmin(head_to_head, axis=1)
        win_probs = np.bincount(win_idx, minlength=2) / request.n_trials
        ties = int(np.sum(best_fixed_totals == reactive_totals))

        return StrategySimulationResponse(
            race_id=race.id,
            driver_code=driver.code,
            current_lap=request.current_lap,
            current_tyre_age=request.current_tyre_age,
            compound=request.compound,
            n_trials=request.n_trials,
            n_remaining_stops=1,
            base_pace_seconds=base.base_pace_seconds,
            base_pace_n_laps_used=base.n_laps_used,
            circuit_name=circuit.name,
            pit_loss_mean_seconds=pit_loss_model.mean_seconds,
            pit_loss_std_seconds=pit_loss_model.std_seconds,
            pit_loss_model_source=pit_loss_source,
            degradation_slope=deg_slope,
            degradation_model_available=degradation_model_available,
            sweep=[SweepPoint(offset=o, mean_seconds=m) for o, m in sweep_means.items()],
            best_fixed_offset=best_fixed_offset,
            best_fixed_mean_seconds=sweep_means[best_fixed_offset],
            reactive=ReactiveStrategyResult(
                window=reactive_window,
                fallback_offset=reactive_fallback,
                mean_seconds=float(reactive_totals.mean()),
            ),
            head_to_head=HeadToHeadResult(
                best_fixed_win_probability=float(win_probs[0]),
                reactive_win_probability=float(win_probs[1]),
                tie_probability=ties / request.n_trials,
            ),
        )

    else:
        # --- n_remaining_stops > 1: multi-stop, multi-compound search ---
        if request.allowed_compounds is not None:
            unknown = [c for c in request.allowed_compounds if c not in predictor.degradation_models]
            if unknown:
                raise HTTPException(
                    status_code=400,
                    detail=f"No fitted degradation model for compound(s): {unknown}. "
                            f"Available: {list(predictor.degradation_models.keys())}",
                )

        best_offsets, best_compounds, _ = find_best_fixed_multi_stop(
            predictor, pit_loss_model, base.base_pace_seconds, request.compound,
            request.current_tyre_age, request.current_lap, race.total_laps,
            request.n_remaining_stops, request.allowed_compounds,
        )
        totals = simulate_multi_stop(
            predictor, pit_loss_model, base.base_pace_seconds,
            request.current_tyre_age, request.current_lap, race.total_laps,
            best_offsets, best_compounds, request.n_trials, rng,
        )

        return StrategySimulationResponse(
            race_id=race.id,
            driver_code=driver.code,
            current_lap=request.current_lap,
            current_tyre_age=request.current_tyre_age,
            compound=request.compound,
            n_trials=request.n_trials,
            n_remaining_stops=request.n_remaining_stops,
            base_pace_seconds=base.base_pace_seconds,
            base_pace_n_laps_used=base.n_laps_used,
            circuit_name=circuit.name,
            pit_loss_mean_seconds=pit_loss_model.mean_seconds,
            pit_loss_std_seconds=pit_loss_model.std_seconds,
            pit_loss_model_source=pit_loss_source,
            degradation_slope=deg_slope,
            degradation_model_available=degradation_model_available,
            multi_stop=MultiStopResult(
                n_stops=request.n_remaining_stops,
                pit_laps=[request.current_lap + o for o in best_offsets],
                stint_compounds=list(best_compounds),
                mean_seconds=float(totals.mean()),
                p10_seconds=float(np.percentile(totals, 10)),
                p90_seconds=float(np.percentile(totals, 90)),
            ),
        )