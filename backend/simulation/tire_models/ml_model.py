"""
F1RaceOps — ML tire degradation model.

Trains a gradient-boosted regressor to predict lap time directly from
tyre_age, lap_number, compound, circuit, and driver — as a comparison
point against the deterministic model (Step 1-4). This is the M5
milestone: a trained model swapped in behind (conceptually) the same
"predict a lap time" interface as the deterministic one, evaluated on
real held-out data rather than assumed to be better just for being ML.

EVALUATION METHODOLOGY — read before trusting the numbers this produces:
Split at the STINT level (an entire stint is either train or test, never
split across both) to avoid leaking a stint's own degradation trend across
the train/test boundary. This is a random split across all 5 circuits'
stints, NOT leave-one-race-out. Leave-one-race-out was considered and
rejected: this project's 5 v1 races map to 5 DIFFERENT circuits (1:1), so
leave-one-race-out would always mean "predict at a circuit the model has
zero information about" — with only 5 circuits total, that measures "how
bad is the model with no track information" rather than anything useful
about the model's actual predictive quality. The random stint-level split
instead tests "does this model capture compound/tyre-age/circuit effects
well, given it has seen the circuit before" — a fairer question for a
dataset this size.

IMPORTANT — this means the MAE reported here is NOT directly comparable to
the deterministic model's 0.826s MAE from Step 4's validation. That number
came from a different protocol (recalibrate per-driver-per-race from early
laps, predict later laps of the SAME driver/race). The two numbers reflect
each model's own natural deployment scenario — the deterministic model
recalibrating live from a race's opening laps, the ML model trained once
on historical data and applied to laps/stints it hasn't specifically seen
before — not a controlled apples-to-apples benchmark. Forcing them onto an
identical protocol would misrepresent one or both models; stating this
plainly is more honest than a misleading single "winner" number.

Usage:
    from backend.database import get_session
    from backend.simulation.tire_models.ml_model import build_lap_dataset, train_and_evaluate
    db = get_session()
    df = build_lap_dataset(db)
    result = train_and_evaluate(df)
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Circuit, Driver, Lap, Race
from backend.simulation.tire_models.deterministic import get_excluded_lap_keys

FEATURE_COLUMNS = ["circuit_ref", "compound", "driver_code", "tyre_age", "lap_number"]
CATEGORICAL_FEATURES = ["circuit_ref", "compound", "driver_code"]
NUMERIC_FEATURES = ["tyre_age", "lap_number"]


@dataclass
class MLModelResult:
    mae: float
    median_ae: float
    p90_ae: float
    n_train_laps: int
    n_test_laps: int
    n_train_stints: int
    n_test_stints: int
    feature_importances: dict = field(default_factory=dict)


def build_lap_dataset(db: Session) -> pd.DataFrame:
    """One row per clean lap (accurate, non-generated, non-in/out-lap) across
    all ingested races, with the features the ML model will train on."""
    in_lap_keys, out_lap_keys = get_excluded_lap_keys(db)

    stmt = (
        select(
            Lap.race_id, Lap.driver_id, Lap.stint_number, Lap.lap_number,
            Lap.lap_time_ms, Lap.tyre_life, Lap.compound,
            Driver.code, Circuit.circuit_ref,
        )
        .join(Driver, Driver.id == Lap.driver_id)
        .join(Race, Race.id == Lap.race_id)
        .join(Circuit, Circuit.id == Race.circuit_id)
        .where(
            Lap.is_accurate.is_(True),
            Lap.is_generated.is_(False),
            Lap.lap_time_ms.is_not(None),
            Lap.tyre_life.is_not(None),
            Lap.compound.is_not(None),
            Lap.stint_number.is_not(None),
        )
    )
    rows = db.execute(stmt).all()

    records = []
    for race_id, driver_id, stint_num, lap_num, lap_time_ms, tyre_life, compound, driver_code, circuit_ref in rows:
        key = (race_id, driver_id, lap_num)
        if key in in_lap_keys or key in out_lap_keys:
            continue
        records.append({
            "stint_key": f"{race_id}_{driver_id}_{stint_num}",
            "circuit_ref": circuit_ref,
            "compound": compound,
            "driver_code": driver_code,
            "tyre_age": float(tyre_life),
            "lap_number": float(lap_num),
            "lap_time_seconds": lap_time_ms / 1000,
        })

    return pd.DataFrame.from_records(records)


def _build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(transformers=[
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ("num", "passthrough", NUMERIC_FEATURES),
    ])
    regressor = GradientBoostingRegressor(
        n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42,
    )
    return Pipeline([("prep", preprocessor), ("reg", regressor)])


def train_and_evaluate(df: pd.DataFrame, test_fraction: float = 0.2, seed: int = 42) -> MLModelResult:
    rng = np.random.default_rng(seed)

    # Converted to a plain list before shuffling: pandas' .unique() can return
    # a StringArray-backed array, which numpy's rng.shuffle explicitly warns
    # may not shuffle correctly (risk of duplicate entries after shuffling) —
    # that would silently corrupt the train/test split. A plain list avoids it.
    unique_stints = list(df["stint_key"].unique())
    rng.shuffle(unique_stints)
    n_test_stints = max(1, int(len(unique_stints) * test_fraction))
    test_stints = set(unique_stints[:n_test_stints])

    is_test = df["stint_key"].isin(test_stints)
    train_df, test_df = df[~is_test].copy(), df[is_test].copy()

    # De-mean the TRAINING target by each circuit's own average lap time
    # (computed from training data only, to avoid leaking test-set laps into
    # the baseline). Without this, absolute lap_time_seconds is dominated by
    # which circuit a lap is from (Montreal ~75s vs Baku ~105s) — the model
    # would trivially "solve" most of its loss just by learning circuit
    # identity, with near-zero incentive to learn the actual tyre-age/
    # compound degradation signal this model exists to capture. Predicting
    # the RESIDUAL from circuit baseline instead forces the model to explain
    # the smaller, more interesting remaining variance.
    global_mean = train_df["lap_time_seconds"].mean()
    circuit_means = train_df.groupby("circuit_ref")["lap_time_seconds"].mean()
    train_df["target_residual"] = train_df["lap_time_seconds"] - train_df["circuit_ref"].map(circuit_means)

    pipeline = _build_pipeline()
    pipeline.fit(train_df[FEATURE_COLUMNS], train_df["target_residual"])

    # Add the circuit baseline back for evaluation, so MAE stays in
    # interpretable seconds and is comparable to the deterministic model's.
    # Falls back to the global mean for a circuit unseen in training (not
    # expected given the stint-level — not circuit-level — split, but
    # handled defensively rather than silently producing a NaN/KeyError).
    test_circuit_baseline = test_df["circuit_ref"].map(circuit_means).fillna(global_mean)
    predicted_residual = pipeline.predict(test_df[FEATURE_COLUMNS])
    predictions = predicted_residual + test_circuit_baseline.values
    errors = np.abs(predictions - test_df["lap_time_seconds"].values)

    feature_names = pipeline.named_steps["prep"].get_feature_names_out()
    importances = pipeline.named_steps["reg"].feature_importances_
    importance_dict = dict(sorted(
        zip(feature_names, importances), key=lambda x: -x[1]
    )[:15])  # top 15 — one-hot expands categories into many columns

    return MLModelResult(
        mae=float(errors.mean()),
        median_ae=float(np.median(errors)),
        p90_ae=float(np.percentile(errors, 90)),
        n_train_laps=len(train_df),
        n_test_laps=len(test_df),
        n_train_stints=len(unique_stints) - n_test_stints,
        n_test_stints=n_test_stints,
        feature_importances=importance_dict,
    )