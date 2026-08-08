"""
F1RaceOps — combined lap-time model.

Combines the three pieces built in Steps 1-3 into a single lap-time
predictor: predicted_lap_time = driver_base_pace + degradation_effect(tyre)
+ fuel_effect(lap_number). This is the deterministic "physics engine"
Phase 4 was scoped to build — the Monte Carlo engine (M6) will randomize
around this rather than the M1 spike's single-stint naive fit.

DESIGN DECISION worth stating explicitly: the degradation regression in
tire_models/deterministic.py also fits a `fuel_slope` coefficient — but
that coefficient exists ONLY to control for fuel burn-off while isolating
the tyre-age effect (see that module's docstring). It's pooled across
circuits and stint lengths in a way that makes it unreliable as a
standalone predictive fuel model for an arbitrary race. This module uses
the physics-based fuel model (fuel_model.py) instead, which generalizes to
any race length rather than being tied to the specific races in the fit.

Base pace estimation: a driver's true "zero wear, zero fuel" pace isn't
directly observable, so it's backed out from their own early-stint laps
(low tyre_age, where degradation is minimal) by subtracting the estimated
fuel effect for that lap. This is itself an approximation — it assumes the
degradation model's slope is accurate for very low tyre ages, and that a
handful of early laps is enough to estimate a stable baseline.
"""

from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Lap, PitStop, Stint
from backend.simulation.fuel_model import estimate_fuel_effect
from backend.simulation.pit_loss_model import (
    PitLossModel,
    fit_pit_loss_models,
    get_global_fallback_model,
)
from backend.simulation.tire_models.deterministic import (
    CompoundDegradationModel,
    get_excluded_lap_keys,
    fit_degradation_models,
)


@dataclass
class BasePaceEstimate:
    driver_id: int
    race_id: int
    base_pace_seconds: float
    n_laps_used: int
    std_seconds: float


class LapTimePredictor:
    """
    Bundles the fitted degradation and pit-loss models so they're only
    fit once (each requires DB queries) and reused across predictions,
    rather than re-fitting per call.
    """

    def __init__(self, db: Session, max_base_pace_tyre_age: int = 3):
        self.degradation_models: dict[str, CompoundDegradationModel] = fit_degradation_models(db)
        self.pit_loss_models: dict[str, PitLossModel] = fit_pit_loss_models(db)
        self.pit_loss_fallback: PitLossModel = get_global_fallback_model(db)
        self.max_base_pace_tyre_age = max_base_pace_tyre_age
        self._db = db

    def get_degradation_slope(self, compound: str) -> float:
        model = self.degradation_models.get(compound)
        if model is None:
            # No fitted model for this compound (too little data — see
            # get_compound_lap_diagnostics). Fall back to zero rather than
            # silently guessing a number with no basis.
            return 0.0
        return model.deg_slope

    def get_pit_loss(self, circuit_ref: str) -> PitLossModel:
        return self.pit_loss_models.get(circuit_ref, self.pit_loss_fallback)

    def estimate_base_pace(self, race_id: int, driver_id: int, total_laps: int) -> BasePaceEstimate | None:
        in_lap_keys, out_lap_keys = get_excluded_lap_keys(self._db)

        stmt = select(
            Lap.lap_number, Lap.lap_time_ms, Lap.tyre_life, Lap.compound,
        ).where(
            Lap.race_id == race_id,
            Lap.driver_id == driver_id,
            Lap.is_accurate.is_(True),
            Lap.is_generated.is_(False),
            Lap.lap_time_ms.is_not(None),
            Lap.tyre_life.is_not(None),
            Lap.tyre_life <= self.max_base_pace_tyre_age,
        )
        rows = self._db.execute(stmt).all()

        residuals = []
        for lap_number, lap_time_ms, tyre_life, compound in rows:
            key = (race_id, driver_id, lap_number)
            if key in in_lap_keys or key in out_lap_keys:
                continue
            deg_slope = self.get_degradation_slope(compound) if compound else 0.0
            fuel_effect = estimate_fuel_effect(lap_number, total_laps).lap_time_delta_seconds
            lap_time_s = lap_time_ms / 1000
            residual = lap_time_s - deg_slope * tyre_life - fuel_effect
            residuals.append(residual)

        if len(residuals) < 2:
            return None

        arr = np.array(residuals)
        return BasePaceEstimate(
            driver_id=driver_id, race_id=race_id,
            base_pace_seconds=float(arr.mean()),
            n_laps_used=len(arr), std_seconds=float(arr.std()),
        )

    def predict_lap_time(self, base_pace_seconds: float, compound: str,
                          tyre_age: int, lap_number: int, total_laps: int) -> float:
        deg_slope = self.get_degradation_slope(compound)
        fuel_effect = estimate_fuel_effect(lap_number, total_laps).lap_time_delta_seconds
        return base_pace_seconds + deg_slope * tyre_age + fuel_effect

    def predict_stint_total_time(self, base_pace_seconds: float, compound: str,
                                  start_tyre_age: int, start_lap: int, end_lap: int,
                                  total_laps: int) -> float:
        """Sum of predicted lap times across [start_lap, end_lap] inclusive,
        with tyre_age incrementing by 1 each lap from start_tyre_age."""
        total = 0.0
        tyre_age = start_tyre_age
        for lap in range(start_lap, end_lap + 1):
            total += self.predict_lap_time(base_pace_seconds, compound, tyre_age, lap, total_laps)
            tyre_age += 1
        return total