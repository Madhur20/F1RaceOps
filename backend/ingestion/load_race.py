"""
F1RaceOps — race ingestion.

Pulls one race session from FastF1 and normalizes it into the schema defined
in backend/models/models.py. Designed to be re-run safely: driver/constructor/
circuit rows are upserted (get-or-create), and re-loading laps/results/etc.
for a race that's already in the DB replaces that race's rows rather than
duplicating them.

Derivation notes (see docs/phase0-plan.md and the M2 planning discussion):
  - Stints are aggregated from FastF1's per-lap `Stint` column (FastF1
    already tags each lap with its stint number — this isn't inferred from
    scratch, just grouped and summarized).
  - Pit stops are inferred from `PitInTime` (marks the in-lap) and
    `PitOutTime` (marks the following out-lap); duration is the gap between
    them.
  - Circuit lat/lng are NOT populated yet — FastF1 doesn't expose overall
    circuit coordinates directly (only per-corner data via get_circuit_info,
    which is a different granularity). Left as NULL for now; a follow-up
    could backfill these from a small manual lookup table if the dashboard
    ends up wanting a map view.

Usage:
    from backend.ingestion.load_race import load_race
    load_race(2023, "Bahrain")
"""

import logging

import fastf1
import numpy as np
import pandas as pd
from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import (
    Circuit,
    Constructor,
    Driver,
    Lap,
    PitStop,
    Race,
    RaceResult,
    Stint,
    Weather,
)

logger = logging.getLogger(__name__)

CACHE_DIR = "./fastf1_cache"
_cache_ready = False


def _ensure_cache() -> None:
    global _cache_ready
    if not _cache_ready:
        import os
        os.makedirs(CACHE_DIR, exist_ok=True)
        fastf1.Cache.enable_cache(CACHE_DIR)
        _cache_ready = True


def _slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace(".", "")


def _timedelta_to_ms(td) -> int | None:
    if td is None or pd.isna(td):
        return None
    return int(td.total_seconds() * 1000)


# --- Upsert helpers -------------------------------------------------------

def get_or_create_driver(session: Session, code: str, given_name: str,
                          family_name: str, nationality: str | None) -> Driver:
    driver_ref = _slugify(f"{given_name}_{family_name}") if given_name else _slugify(code)
    driver = session.query(Driver).filter_by(driver_ref=driver_ref).one_or_none()
    if driver is None:
        driver = Driver(
            driver_ref=driver_ref, code=code, given_name=given_name,
            family_name=family_name, nationality=nationality,
        )
        session.add(driver)
        session.flush()  # populate driver.id without a full commit
    return driver


def get_or_create_constructor(session: Session, name: str, nationality: str | None) -> Constructor:
    constructor_ref = _slugify(name)
    constructor = session.query(Constructor).filter_by(constructor_ref=constructor_ref).one_or_none()
    if constructor is None:
        constructor = Constructor(constructor_ref=constructor_ref, name=name, nationality=nationality)
        session.add(constructor)
        session.flush()
    return constructor


def get_or_create_circuit(session: Session, name: str, country: str | None) -> Circuit:
    circuit_ref = _slugify(name)
    circuit = session.query(Circuit).filter_by(circuit_ref=circuit_ref).one_or_none()
    if circuit is None:
        # lat/lng intentionally left NULL — see module docstring
        circuit = Circuit(circuit_ref=circuit_ref, name=name, country=country, lat=None, lng=None)
        session.add(circuit)
        session.flush()
    return circuit


def get_or_create_race(session: Session, season: int, round_number: int, name: str,
                        circuit: Circuit, race_date, total_laps: int | None) -> Race:
    race = session.query(Race).filter_by(season=season, round=round_number).one_or_none()
    if race is None:
        race = Race(
            season=season, round=round_number, circuit_id=circuit.id,
            race_date=race_date, name=name, total_laps=total_laps,
        )
        session.add(race)
        session.flush()
    return race


def _clear_existing_race_data(session: Session, race_id: int) -> None:
    """Delete this race's existing laps/results/stints/pit_stops/weather so a
    re-run replaces rather than duplicates them."""
    for model in (Lap, RaceResult, Stint, PitStop, Weather):
        session.execute(delete(model).where(model.race_id == race_id))


# --- Main ingestion ---------------------------------------------------------

def load_race(year: int, event: str) -> Race:
    _ensure_cache()
    logger.info("Loading %s %s from FastF1...", year, event)

    session_f1 = fastf1.get_session(year, event, "R")
    session_f1.load(laps=True, telemetry=False, weather=True)

    results_df = session_f1.results
    laps_df = session_f1.laps
    weather_df = session_f1.weather_data

    db = get_session()
    try:
        circuit = get_or_create_circuit(
            db,
            name=session_f1.event.get("Location", event),
            country=session_f1.event.get("Country"),
        )
        race = get_or_create_race(
            db,
            season=year,
            round_number=int(session_f1.event.get("RoundNumber", 0)),
            name=session_f1.event.get("EventName", event),
            circuit=circuit,
            race_date=session_f1.event.get("EventDate"),
            total_laps=int(laps_df["LapNumber"].max()) if not laps_df.empty else None,
        )
        _clear_existing_race_data(db, race.id)
        db.flush()

        # driver/constructor lookups, built once from results_df
        driver_lookup: dict[str, Driver] = {}
        constructor_lookup: dict[str, Constructor] = {}

        for _, row in results_df.iterrows():
            driver = get_or_create_driver(
                db,
                code=row.get("Abbreviation"),
                given_name=row.get("FirstName", ""),
                family_name=row.get("LastName", ""),
                nationality=row.get("CountryCode"),
            )
            constructor = get_or_create_constructor(
                db,
                name=row.get("TeamName", "Unknown"),
                nationality=None,
            )
            driver_lookup[row["Abbreviation"]] = driver
            constructor_lookup[row["Abbreviation"]] = constructor

            db.add(RaceResult(
                race_id=race.id,
                driver_id=driver.id,
                constructor_id=constructor.id,
                grid_position=_safe_int(row.get("GridPosition")),
                finish_position=_safe_int(row.get("Position")),
                status=row.get("Status"),
                points=float(row["Points"]) if pd.notna(row.get("Points")) else None,
            ))

        db.flush()
        logger.info("  %d drivers, %d results", len(driver_lookup), len(results_df))

        _load_laps(db, race, laps_df, driver_lookup)
        _load_stints(db, race, laps_df, driver_lookup)
        _load_pit_stops(db, race, laps_df, driver_lookup)
        _load_weather(db, race, weather_df)

        db.commit()
        logger.info("Committed %s %s (race_id=%d)", year, event, race.id)
        return race

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _safe_int(value) -> int | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return int(value)


def _load_laps(db: Session, race: Race, laps_df: pd.DataFrame,
               driver_lookup: dict[str, Driver]) -> None:
    count = 0
    for _, lap in laps_df.iterrows():
        driver = driver_lookup.get(lap["Driver"])
        if driver is None:
            continue  # driver not in results (e.g. DNS) — skip rather than guess
        db.add(Lap(
            race_id=race.id,
            driver_id=driver.id,
            lap_number=int(lap["LapNumber"]),
            lap_time_ms=_timedelta_to_ms(lap.get("LapTime")),
            cumulative_time_ms=_timedelta_to_ms(lap.get("Time")),
            position=_safe_int(lap.get("Position")),
            sector_1_ms=_timedelta_to_ms(lap.get("Sector1Time")),
            sector_2_ms=_timedelta_to_ms(lap.get("Sector2Time")),
            sector_3_ms=_timedelta_to_ms(lap.get("Sector3Time")),
            compound=lap.get("Compound"),
            tyre_life=_safe_int(lap.get("TyreLife")),
            stint_number=_safe_int(lap.get("Stint")),
            is_accurate=bool(lap.get("IsAccurate", False)),
            is_generated=bool(lap.get("FastF1Generated", False)),
        ))
        count += 1
    db.flush()
    logger.info("  %d laps", count)


def _load_stints(db: Session, race: Race, laps_df: pd.DataFrame,
                  driver_lookup: dict[str, Driver]) -> None:
    """Aggregate FastF1's per-lap Stint column into stint-level rows."""
    count = 0
    for (drv_code, stint_num), stint_laps in laps_df.groupby(["Driver", "Stint"]):
        driver = driver_lookup.get(drv_code)
        if driver is None or pd.isna(stint_num):
            continue
        compounds = stint_laps["Compound"].dropna()
        compound = compounds.mode().iloc[0] if not compounds.empty else None
        db.add(Stint(
            race_id=race.id,
            driver_id=driver.id,
            stint_number=int(stint_num),
            compound=compound,
            lap_start=int(stint_laps["LapNumber"].min()),
            lap_end=int(stint_laps["LapNumber"].max()),
            tyre_life_start=_safe_int(stint_laps["TyreLife"].min()),
        ))
        count += 1
    db.flush()
    logger.info("  %d stints", count)


def _load_pit_stops(db: Session, race: Race, laps_df: pd.DataFrame,
                     driver_lookup: dict[str, Driver]) -> None:
    """
    Infer pit stops from PitInTime (in-lap) / PitOutTime (out-lap). A stop's
    duration is approximated as the gap between the in-lap's PitInTime and
    the following out-lap's PitOutTime.
    """
    count = 0
    for drv_code, driver_laps in laps_df.groupby("Driver"):
        driver = driver_lookup.get(drv_code)
        if driver is None:
            continue
        driver_laps = driver_laps.sort_values("LapNumber")
        in_laps = driver_laps[driver_laps["PitInTime"].notna()]

        stop_number = 0
        for _, in_lap in in_laps.iterrows():
            out_candidates = driver_laps[driver_laps["LapNumber"] > in_lap["LapNumber"]]
            out_lap = out_candidates[out_candidates["PitOutTime"].notna()].head(1)
            if out_lap.empty:
                continue
            duration_ms = _timedelta_to_ms(
                out_lap.iloc[0]["PitOutTime"] - in_lap["PitInTime"]
            )
            stop_number += 1
            db.add(PitStop(
                race_id=race.id,
                driver_id=driver.id,
                lap_number=int(in_lap["LapNumber"]),
                duration_ms=duration_ms,
                stop_number=stop_number,
            ))
            count += 1
    db.flush()
    logger.info("  %d pit stops", count)


def _load_weather(db: Session, race: Race, weather_df: pd.DataFrame) -> None:
    """
    FastF1 weather data is time-indexed (roughly one reading per minute),
    not lap-indexed. Approximate a lap number for each reading by even
    distribution across the session time range, then bucket multiple
    readings that land on the same lap into a single averaged row — the
    `weather` table has a unique (race_id, lap_number) constraint, so
    inserting one row per raw reading would collide whenever more than one
    reading maps to the same lap (routine, given ~1 reading/minute vs.
    ~1-2 minutes/lap). Coarse, but sufficient for "was it raining around
    lap N" queries; refine later if per-lap precision turns out to matter.
    """
    if weather_df.empty or race.total_laps is None:
        return

    session_start = weather_df["Time"].min()
    session_end = weather_df["Time"].max()
    session_span = (session_end - session_start).total_seconds() or 1.0

    df = weather_df.copy()
    df["approx_lap"] = df["Time"].apply(
        lambda t: max(1, min(race.total_laps,
                              round(((t - session_start).total_seconds() / session_span) * race.total_laps)))
    )

    count = 0
    for lap_number, group in df.groupby("approx_lap"):
        db.add(Weather(
            race_id=race.id,
            lap_number=int(lap_number),
            air_temp=float(group["AirTemp"].mean()) if group["AirTemp"].notna().any() else None,
            track_temp=float(group["TrackTemp"].mean()) if group["TrackTemp"].notna().any() else None,
            humidity=float(group["Humidity"].mean()) if group["Humidity"].notna().any() else None,
            rainfall=bool(group["Rainfall"].any()) if "Rainfall" in group else False,
            wind_speed=float(group["WindSpeed"].mean()) if group["WindSpeed"].notna().any() else None,
        ))
        count += 1
    db.flush()
    logger.info("  %d weather readings (bucketed to %d unique laps)", len(df), count)