"""
F1RaceOps — race state engine.

Computes "what does the race look like at lap N" from the data layer built
in M2. This is the input every strategy simulation (Phase 4+) will consume.

Gap calculations use Lap.cumulative_time_ms, which is sourced directly from
FastF1's own Time column (session-elapsed time at the end of each lap) —
NOT reconstructed by summing individual lap_time_ms values. An earlier
version did sum lap times, which turned out to be fragile: a single missing
lap_time_ms anywhere in a driver's race broke their cumulative total for
every subsequent lap. Reading FastF1's own cumulative field avoids that
class of bug entirely rather than working around it.

Known limitation, stated plainly rather than silently estimated as if real:
FastF1 does not provide fuel load data at all. `estimated_fuel_remaining_pct`
is a simple linear depletion model (100% at lap 1, 0% at the final lap) —
not measured telemetry. Good enough as a placeholder input to the physics
engine (Phase 4), not something to present as ground truth.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Driver, Lap, Race, Weather
from backend.schemas.race_state import DriverState, RaceStateSnapshot, WeatherSnapshot


def _get_weather_at_lap(db: Session, race_id: int, lap_number: int) -> WeatherSnapshot | None:
    """Weather is bucketed per-lap but not every lap necessarily has a row
    (see M2 ingestion notes) — fall back to the nearest available lap <= N."""
    stmt = (
        select(Weather)
        .where(Weather.race_id == race_id, Weather.lap_number <= lap_number)
        .order_by(Weather.lap_number.desc())
        .limit(1)
    )
    weather = db.execute(stmt).scalars().first()
    if weather is None:
        return None
    return WeatherSnapshot(
        air_temp=weather.air_temp,
        track_temp=weather.track_temp,
        humidity=weather.humidity,
        rainfall=weather.rainfall,
        wind_speed=weather.wind_speed,
    )


def get_race_state(db: Session, race_id: int, lap_number: int) -> RaceStateSnapshot | None:
    race = db.get(Race, race_id)
    if race is None:
        return None

    # one row per driver: their Lap record at exactly this lap number
    stmt = (
        select(Lap)
        .where(Lap.race_id == race_id, Lap.lap_number == lap_number)
        .order_by(Lap.position)
    )
    laps_at_n = db.execute(stmt).scalars().all()

    # sort by position for gap-ahead comparisons. Drivers with a null Position
    # for this specific lap (an occasional real FastF1 data gap) are kept, not
    # dropped — sorted to the end rather than excluded from the snapshot.
    laps_sorted = sorted(
        laps_at_n,
        key=lambda lap: (lap.position is None, lap.position if lap.position is not None else 0),
    )

    # Reference point for gap_to_leader: the minimum cumulative_time_ms among
    # drivers who have it — should now be nearly everyone, since this field
    # comes straight from FastF1's own Time column rather than a fragile
    # per-lap summation.
    valid_times = [lap.cumulative_time_ms for lap in laps_at_n if lap.cumulative_time_ms is not None]
    leader_time = min(valid_times) if valid_times else None

    driver_states: list[DriverState] = []
    prev_time_ms: int | None = None
    for lap in laps_sorted:
        driver: Driver | None = lap.driver
        my_time = lap.cumulative_time_ms

        gap_to_leader = None
        if my_time is not None and leader_time is not None:
            gap_to_leader = (my_time - leader_time) / 1000

        gap_ahead = None
        if my_time is not None and prev_time_ms is not None:
            gap_ahead = (my_time - prev_time_ms) / 1000

        driver_states.append(DriverState(
            driver_code=driver.code if driver else "UNK",
            position=lap.position,
            gap_to_leader_seconds=gap_to_leader,
            gap_ahead_seconds=gap_ahead,
            compound=lap.compound,
            tyre_age=lap.tyre_life,
            stint_number=lap.stint_number,
            estimated_fuel_remaining_pct=_estimate_fuel_pct(lap_number, race.total_laps),
        ))
        prev_time_ms = my_time

    return RaceStateSnapshot(
        race_id=race.id,
        lap_number=lap_number,
        total_laps=race.total_laps,
        weather=_get_weather_at_lap(db, race_id, lap_number),
        drivers=driver_states,
    )


def _estimate_fuel_pct(lap_number: int, total_laps: int | None) -> float | None:
    """Linear depletion placeholder — see module docstring. NOT real telemetry."""
    if not total_laps or total_laps <= 0:
        return None
    remaining = max(0.0, 1.0 - (lap_number - 1) / total_laps)
    return round(remaining * 100, 1)