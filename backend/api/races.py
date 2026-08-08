"""
F1RaceOps — /races API router.

Endpoints (per the Phase 0 API contract, docs/phase0-plan.md section 4):
    GET /races                  list races, optional ?season= filter
    GET /races/{race_id}        one race, with circuit detail
    GET /races/{race_id}/laps   laps for a race, optional ?driver=CODE filter
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Driver, Lap, Race
from backend.schemas import LapOut, RaceDetail, RaceSummary
from backend.schemas.race_state import RaceStateSnapshot
from backend.services import get_race_state

router = APIRouter(prefix="/races", tags=["races"])


@router.get("", response_model=list[RaceSummary])
def list_races(
    season: int | None = Query(None, description="Filter to a specific season, e.g. 2023"),
    db: Session = Depends(get_db),
):
    stmt = select(Race).order_by(Race.season, Race.round)
    if season is not None:
        stmt = stmt.where(Race.season == season)
    races = db.execute(stmt).scalars().all()
    return races  # RaceSummary fields all map directly — from_attributes handles this


@router.get("/{race_id}", response_model=RaceDetail)
def get_race(race_id: int, db: Session = Depends(get_db)):
    race = db.get(Race, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail=f"Race {race_id} not found")

    return RaceDetail(
        id=race.id,
        season=race.season,
        round=race.round,
        name=race.name,
        race_date=race.race_date,
        total_laps=race.total_laps,
        circuit_name=race.circuit.name if race.circuit else None,
        circuit_country=race.circuit.country if race.circuit else None,
    )


@router.get("/{race_id}/laps", response_model=list[LapOut])
def get_race_laps(
    race_id: int,
    driver: str | None = Query(None, description="Filter to one driver's code, e.g. VER"),
    accurate_only: bool = Query(False, description="Only return laps flagged IsAccurate by FastF1"),
    db: Session = Depends(get_db),
):
    race = db.get(Race, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail=f"Race {race_id} not found")

    stmt = select(Lap).where(Lap.race_id == race_id).order_by(Lap.driver_id, Lap.lap_number)
    if driver is not None:
        stmt = stmt.join(Driver).where(Driver.code == driver.upper())
    if accurate_only:
        stmt = stmt.where(Lap.is_accurate.is_(True))

    laps = db.execute(stmt).scalars().all()

    return [
        LapOut(
            lap_number=lap.lap_number,
            driver_code=lap.driver.code if lap.driver else None,
            lap_time_seconds=(lap.lap_time_ms / 1000) if lap.lap_time_ms is not None else None,
            position=lap.position,
            compound=lap.compound,
            tyre_life=lap.tyre_life,
            stint_number=lap.stint_number,
            is_accurate=lap.is_accurate,
        )
        for lap in laps
    ]


@router.get("/{race_id}/state", response_model=RaceStateSnapshot)
def get_race_state_snapshot(
    race_id: int,
    lap: int = Query(..., ge=1, description="Lap number to snapshot the race state at"),
    db: Session = Depends(get_db),
):
    race = db.get(Race, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail=f"Race {race_id} not found")
    if race.total_laps is not None and lap > race.total_laps:
        raise HTTPException(
            status_code=400,
            detail=f"Race {race_id} only has {race.total_laps} laps; lap {lap} is out of range.",
        )

    snapshot = get_race_state(db, race_id, lap)
    if snapshot is None or not snapshot.drivers:
        raise HTTPException(
            status_code=404,
            detail=f"No lap data found for race {race_id} at lap {lap}.",
        )
    return snapshot