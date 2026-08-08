"""
F1RaceOps — race state snapshot schemas.

Represents "what does the race look like at lap N" — the core input to
every strategy simulation from here on.
"""

from pydantic import BaseModel


class DriverState(BaseModel):
    driver_code: str
    position: int | None
    gap_to_leader_seconds: float | None = None  # None if data is incomplete, not zero
    gap_ahead_seconds: float | None = None
    compound: str | None
    tyre_age: int | None
    stint_number: int | None
    estimated_fuel_remaining_pct: float | None = None  # ESTIMATE — see race_state.py docstring


class WeatherSnapshot(BaseModel):
    air_temp: float | None
    track_temp: float | None
    humidity: float | None
    rainfall: bool
    wind_speed: float | None


class RaceStateSnapshot(BaseModel):
    race_id: int
    lap_number: int
    total_laps: int | None
    weather: WeatherSnapshot | None
    drivers: list[DriverState]