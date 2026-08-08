"""
F1RaceOps — Pydantic response schemas for the races/laps API.

Kept separate from backend/models (the SQLAlchemy ORM models) on purpose:
these define what the API returns over the wire, which is deliberately a
narrower, friendlier view than the full database row (e.g. lap times come
out in seconds here, not the raw milliseconds stored in the DB).
"""

import datetime

from pydantic import BaseModel, ConfigDict


class RaceSummary(BaseModel):
    """Used by GET /races — one row per race, no nested detail."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    season: int
    round: int
    name: str
    race_date: datetime.date | None
    total_laps: int | None


class RaceDetail(RaceSummary):
    """Used by GET /races/{id} — adds circuit info beyond the summary."""
    circuit_name: str | None = None
    circuit_country: str | None = None


class LapOut(BaseModel):
    """Used by GET /races/{id}/laps — one row per lap."""
    model_config = ConfigDict(from_attributes=True)

    lap_number: int
    driver_code: str | None = None
    lap_time_seconds: float | None = None
    position: int | None
    compound: str | None
    tyre_life: int | None
    stint_number: int | None
    is_accurate: bool