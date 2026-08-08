"""
F1RaceOps — deterministic tire degradation model.

Fits a per-compound degradation slope (seconds lost per lap of tyre age)
from ALL ingested race data, while separating it from the confounding
effect of fuel burn-off (car gets lighter, and faster, as a race goes on).

IMPORTANT — why this is fit pooled across stints, not per stint:
Within a single stint, tyre_age and lap_number differ only by a constant
(the stint's starting lap number) — they are perfectly collinear. A
regression on a single stint's laps literally cannot distinguish "the tyres
are degrading" from "the fuel is burning off," because those two candidate
explanations produce identical predictions within that stint. The variation
needed to tell them apart only exists ACROSS stints: a pit stop resets
tyre_age to 0 while lap_number keeps climbing, so pooling many stints
together (each with a different lap_number-to-tyre_age offset) gives the
regression the leverage it needs to separate the two effects. Fitting
per-stint first and averaging afterward — the M1 spike's and this file's
first draft's approach — cannot recover this distinction at all, which is
exactly why the first version of this model showed a confusing negative
degradation slope: it was actually catching mostly the fuel effect for the
more durable compounds.

Per-race fixed effects are included in the regression (a dummy variable per
race, one dropped as reference) to absorb each circuit's own baseline pace
and degradation character — without this, a first version of this model
showed a physically implausible slope ordering (HARD degrading faster than
SOFT) because compound choice correlates with circuit, and the fit was
partly picking up "which circuit" rather than "which compound." Adding
race-level dummies is safe here (unlike a stint-level version, which would
destroy the tyre/fuel identification above) — multiple stints still exist
within a single race, so the needed variation survives.

Usage:
    from backend.database import get_session
    from backend.simulation.tire_models.deterministic import fit_degradation_models
    db = get_session()
    models = fit_degradation_models(db)
    models["SOFT"].deg_slope, models["SOFT"].fuel_slope, ...
"""

from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Lap, PitStop, Stint


@dataclass
class CompoundDegradationModel:
    compound: str
    deg_slope: float           # seconds lost per lap of TYRE AGE, fuel effect controlled for
    deg_slope_se: float        # standard error of deg_slope
    fuel_slope: float          # seconds gained (negative) per LAP of the race, tyre age controlled for
    fuel_slope_se: float
    n_stints: int
    n_laps: int


def get_excluded_lap_keys(db: Session) -> tuple[set, set]:
    """Returns (in_lap_keys, out_lap_keys), each a set of (race_id, driver_id,
    lap_number) tuples to exclude — pit-affected laps, not degradation signal."""
    pit_stops = db.execute(select(PitStop.race_id, PitStop.driver_id, PitStop.lap_number)).all()
    in_lap_keys = {(r, d, l) for r, d, l in pit_stops}

    stints = db.execute(select(Stint.race_id, Stint.driver_id, Stint.lap_start)).all()
    out_lap_keys = {(r, d, l) for r, d, l in stints}

    return in_lap_keys, out_lap_keys


def get_compound_lap_diagnostics(db: Session) -> dict[str, dict]:
    """
    Diagnostic helper: shows, per compound, how many laps survive each
    filtering stage. Useful for answering "why does compound X have no
    fitted model" without guessing — e.g. WET tyres may simply have very
    few laps in the ingested race set, or most of them may fall on
    in-laps/out-laps in short wet stints.
    """
    in_lap_keys, out_lap_keys = get_excluded_lap_keys(db)

    all_laps = db.execute(select(
        Lap.race_id, Lap.driver_id, Lap.lap_number, Lap.compound,
        Lap.is_accurate, Lap.is_generated, Lap.lap_time_ms, Lap.tyre_life, Lap.stint_number,
    )).all()

    diagnostics: dict[str, dict] = {}
    for race_id, driver_id, lap_num, compound, is_accurate, is_generated, lap_time_ms, tyre_life, stint_num in all_laps:
        if compound is None:
            continue
        d = diagnostics.setdefault(compound, {
            "total_laps": 0, "accurate_clean_laps": 0, "after_inout_exclusion": 0,
        })
        d["total_laps"] += 1
        if is_accurate and not is_generated and lap_time_ms is not None and tyre_life is not None and stint_num is not None:
            d["accurate_clean_laps"] += 1
            key = (race_id, driver_id, lap_num)
            if key not in in_lap_keys and key not in out_lap_keys:
                d["after_inout_exclusion"] += 1
    return diagnostics


def fit_degradation_models(db: Session, min_stints: int = 2, min_laps: int = 15) -> dict[str, CompoundDegradationModel]:
    """
    min_stints: a compound needs laps from at least this many distinct
    stints to have any chance of separating tyre age from fuel burn at all
    (see module docstring) — below this, the two effects are unidentifiable
    regardless of how many laps exist.
    """
    in_lap_keys, out_lap_keys = get_excluded_lap_keys(db)

    stmt = select(
        Lap.race_id, Lap.driver_id, Lap.stint_number, Lap.lap_number,
        Lap.lap_time_ms, Lap.tyre_life, Lap.compound,
    ).where(
        Lap.is_accurate.is_(True),
        Lap.is_generated.is_(False),
        Lap.lap_time_ms.is_not(None),
        Lap.tyre_life.is_not(None),
        Lap.compound.is_not(None),
        Lap.stint_number.is_not(None),
    )
    rows = db.execute(stmt).all()

    # group clean (non-in/out-lap) laps by compound, pooled across ALL stints
    by_compound: dict[str, list[tuple]] = {}
    for race_id, driver_id, stint_num, lap_num, lap_time_ms, tyre_life, compound in rows:
        key = (race_id, driver_id, lap_num)
        if key in in_lap_keys or key in out_lap_keys:
            continue
        stint_key = (race_id, driver_id, stint_num)
        by_compound.setdefault(compound, []).append(
            (float(tyre_life), float(lap_num), lap_time_ms / 1000, stint_key, race_id)
        )

    models: dict[str, CompoundDegradationModel] = {}
    for compound, points in by_compound.items():
        n_stints = len({p[3] for p in points})
        if len(points) < min_laps or n_stints < min_stints:
            continue  # not enough data, or not enough distinct stints to identify the two effects

        tyre_age = np.array([p[0] for p in points])
        lap_number = np.array([p[1] for p in points])
        lap_time = np.array([p[2] for p in points])
        race_ids = [p[4] for p in points]

        # Per-race fixed effects: absorb each circuit's baseline pace/degradation
        # character so the fitted compound slope isn't confounded by which
        # circuits happened to use that compound most. Safe to add (unlike a
        # stint-level version) since multiple stints still exist within a race,
        # preserving the tyre_age/lap_number separation described above.
        # One race is dropped as the reference level to avoid collinearity
        # with the intercept column.
        unique_races = sorted(set(race_ids))
        race_dummy_cols = []
        for race_id in unique_races[1:]:
            race_dummy_cols.append([1.0 if r == race_id else 0.0 for r in race_ids])

        X_columns = [np.ones(len(points)), tyre_age, lap_number] + [np.array(c) for c in race_dummy_cols]
        X = np.column_stack(X_columns)
        coeffs, _, _, _ = np.linalg.lstsq(X, lap_time, rcond=None)

        n, k = X.shape
        if n > k:
            residuals = lap_time - X @ coeffs
            sigma2 = (residuals @ residuals) / (n - k)
            cov = sigma2 * np.linalg.inv(X.T @ X)
            se = np.sqrt(np.diag(cov))
        else:
            se = np.full(k, np.nan)

        models[compound] = CompoundDegradationModel(
            compound=compound,
            deg_slope=float(coeffs[1]),
            deg_slope_se=float(se[1]),
            fuel_slope=float(coeffs[2]),
            fuel_slope_se=float(se[2]),
            n_stints=n_stints,
            n_laps=len(points),
        )

    return models