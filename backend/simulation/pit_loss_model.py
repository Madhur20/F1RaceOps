"""
F1RaceOps — pit-loss model.

Fits mean/std pit-lane loss PER CIRCUIT from real pit_stops data, replacing
the M1 spike's flat placeholder (22.5s +/- 1.5s for every circuit, made up
rather than measured).

duration_ms is PitOutTime - PitInTime — the full pit-lane transit loss
(entry + stationary stop + exit), not just the few-second stationary tire
change. That's intentional and correct for this use case: the Monte Carlo
model needs "total time lost relative to staying on track," which is
exactly what this captures.

Outlier handling: a small number of "pit stops" in real data are not
normal tire changes — drive-through penalties, damage-related stops, or a
car retiring in the pits. These would skew the mean upward if included
uncritically. Filtered via a simple IQR rule per circuit rather than a
fixed cutoff, since normal pit-lane loss itself varies meaningfully by
circuit (a long pit lane naturally has a higher baseline than a short one).
"""

from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Circuit, PitStop, Race


@dataclass
class PitLossModel:
    circuit_ref: str
    circuit_name: str
    mean_seconds: float
    std_seconds: float
    n_stops: int
    n_excluded_outliers: int


def _iqr_filter(values: np.ndarray, k: float = 1.5) -> np.ndarray:
    """Standard IQR outlier rule: keep values within k * IQR of Q1/Q3."""
    q1, q3 = np.percentile(values, [25, 75])
    iqr = q3 - q1
    lower, upper = q1 - k * iqr, q3 + k * iqr
    return values[(values >= lower) & (values <= upper)]


def fit_pit_loss_models(db: Session, min_stops: int = 3) -> dict[str, PitLossModel]:
    stmt = (
        select(Circuit.circuit_ref, Circuit.name, PitStop.duration_ms)
        .join(Race, Race.id == PitStop.race_id)
        .join(Circuit, Circuit.id == Race.circuit_id)
        .where(PitStop.duration_ms.is_not(None))
    )
    rows = db.execute(stmt).all()

    by_circuit: dict[str, list[float]] = {}
    circuit_names: dict[str, str] = {}
    for circuit_ref, circuit_name, duration_ms in rows:
        by_circuit.setdefault(circuit_ref, []).append(duration_ms / 1000)
        circuit_names[circuit_ref] = circuit_name

    models: dict[str, PitLossModel] = {}
    for circuit_ref, durations in by_circuit.items():
        arr = np.array(durations)
        if len(arr) < min_stops:
            continue
        filtered = _iqr_filter(arr)
        if len(filtered) < 2:
            continue  # too few left after filtering to compute a meaningful std
        models[circuit_ref] = PitLossModel(
            circuit_ref=circuit_ref,
            circuit_name=circuit_names[circuit_ref],
            mean_seconds=float(filtered.mean()),
            std_seconds=float(filtered.std()),
            n_stops=len(filtered),
            n_excluded_outliers=len(arr) - len(filtered),
        )

    return models


def get_global_fallback_model(db: Session) -> PitLossModel:
    """
    A single global model, pooled across all circuits — used as a fallback
    for a circuit with too few stops to fit its own model (not currently
    hit by the 5-race v1 set, but the simulation layer will eventually need
    to handle circuits it hasn't seen pit data for).
    """
    stmt = select(PitStop.duration_ms).where(PitStop.duration_ms.is_not(None))
    durations = np.array([d / 1000 for (d,) in db.execute(stmt).all()])
    filtered = _iqr_filter(durations)
    return PitLossModel(
        circuit_ref="__global__",
        circuit_name="All circuits (fallback)",
        mean_seconds=float(filtered.mean()),
        std_seconds=float(filtered.std()),
        n_stops=len(filtered),
        n_excluded_outliers=len(durations) - len(filtered),
    )