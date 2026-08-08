"""
F1RaceOps — SQLAlchemy models

Direct translation of the Phase 0 schema sketch (docs/phase0-plan.md, section 3)
into real tables. A few additions beyond the original sketch, called out inline:

  - laps.is_accurate / laps.is_generated: mirrors FastF1's IsAccurate and
    FastF1Generated flags. These are exactly the fields verify_telemetry.py
    checks before a race is trusted — storing them means every future query
    against `laps` can filter on data quality directly in SQL, rather than
    re-deriving it from FastF1 each time.
  - Unique constraints on natural keys (season+round, race+driver+lap, etc.)
    so a re-run of ingestion is safe to repeat (upsert-friendly) rather than
    silently duplicating rows.
"""

import datetime

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_ref: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    code: Mapped[str | None] = mapped_column(String(3))  # e.g. "VER"
    given_name: Mapped[str] = mapped_column(String(100))
    family_name: Mapped[str] = mapped_column(String(100))
    nationality: Mapped[str | None] = mapped_column(String(100))

    results: Mapped[list["RaceResult"]] = relationship(back_populates="driver")
    laps: Mapped[list["Lap"]] = relationship(back_populates="driver")


class Constructor(Base):
    __tablename__ = "constructors"

    id: Mapped[int] = mapped_column(primary_key=True)
    constructor_ref: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    nationality: Mapped[str | None] = mapped_column(String(100))

    results: Mapped[list["RaceResult"]] = relationship(back_populates="constructor")


class Circuit(Base):
    __tablename__ = "circuits"

    id: Mapped[int] = mapped_column(primary_key=True)
    circuit_ref: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(100))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)

    races: Mapped[list["Race"]] = relationship(back_populates="circuit")


class Race(Base):
    __tablename__ = "races"
    __table_args__ = (UniqueConstraint("season", "round", name="uq_race_season_round"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    round: Mapped[int] = mapped_column(Integer)
    circuit_id: Mapped[int] = mapped_column(ForeignKey("circuits.id"))
    race_date: Mapped[datetime.date | None] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(200))
    total_laps: Mapped[int | None] = mapped_column(Integer)

    circuit: Mapped["Circuit"] = relationship(back_populates="races")
    results: Mapped[list["RaceResult"]] = relationship(back_populates="race")
    laps: Mapped[list["Lap"]] = relationship(back_populates="race")
    stints: Mapped[list["Stint"]] = relationship(back_populates="race")
    pit_stops: Mapped[list["PitStop"]] = relationship(back_populates="race")
    weather_readings: Mapped[list["Weather"]] = relationship(back_populates="race")


class RaceResult(Base):
    __tablename__ = "race_results"
    __table_args__ = (UniqueConstraint("race_id", "driver_id", name="uq_result_race_driver"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    race_id: Mapped[int] = mapped_column(ForeignKey("races.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    constructor_id: Mapped[int] = mapped_column(ForeignKey("constructors.id"))
    grid_position: Mapped[int | None] = mapped_column(Integer)
    finish_position: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(100))  # e.g. "Finished", "Retired"
    points: Mapped[float | None] = mapped_column(Float)

    race: Mapped["Race"] = relationship(back_populates="results")
    driver: Mapped["Driver"] = relationship(back_populates="results")
    constructor: Mapped["Constructor"] = relationship(back_populates="results")


class Lap(Base):
    __tablename__ = "laps"
    __table_args__ = (
        UniqueConstraint("race_id", "driver_id", "lap_number", name="uq_lap_race_driver_lapnum"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    race_id: Mapped[int] = mapped_column(ForeignKey("races.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    lap_number: Mapped[int] = mapped_column(Integer)
    lap_time_ms: Mapped[int | None] = mapped_column(Integer)  # milliseconds, not float seconds
    cumulative_time_ms: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int | None] = mapped_column(Integer)
    sector_1_ms: Mapped[int | None] = mapped_column(Integer)
    sector_2_ms: Mapped[int | None] = mapped_column(Integer)
    sector_3_ms: Mapped[int | None] = mapped_column(Integer)
    compound: Mapped[str | None] = mapped_column(String(20))  # SOFT / MEDIUM / HARD / INTERMEDIATE / WET
    tyre_life: Mapped[int | None] = mapped_column(Integer)
    stint_number: Mapped[int | None] = mapped_column(Integer)

    # Mirrors FastF1's IsAccurate / FastF1Generated flags — see module docstring.
    is_accurate: Mapped[bool] = mapped_column(Boolean, default=False)
    is_generated: Mapped[bool] = mapped_column(Boolean, default=False)

    race: Mapped["Race"] = relationship(back_populates="laps")
    driver: Mapped["Driver"] = relationship(back_populates="laps")


class Stint(Base):
    __tablename__ = "stints"
    __table_args__ = (
        UniqueConstraint("race_id", "driver_id", "stint_number", name="uq_stint_race_driver_num"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    race_id: Mapped[int] = mapped_column(ForeignKey("races.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    stint_number: Mapped[int] = mapped_column(Integer)
    compound: Mapped[str | None] = mapped_column(String(20))
    lap_start: Mapped[int] = mapped_column(Integer)
    lap_end: Mapped[int] = mapped_column(Integer)
    tyre_life_start: Mapped[int | None] = mapped_column(Integer)

    race: Mapped["Race"] = relationship(back_populates="stints")


class PitStop(Base):
    __tablename__ = "pit_stops"
    __table_args__ = (
        UniqueConstraint("race_id", "driver_id", "stop_number", name="uq_pitstop_race_driver_num"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    race_id: Mapped[int] = mapped_column(ForeignKey("races.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    lap_number: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    stop_number: Mapped[int] = mapped_column(Integer)

    race: Mapped["Race"] = relationship(back_populates="pit_stops")


class Weather(Base):
    __tablename__ = "weather"
    __table_args__ = (UniqueConstraint("race_id", "lap_number", name="uq_weather_race_lapnum"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    race_id: Mapped[int] = mapped_column(ForeignKey("races.id"), index=True)
    lap_number: Mapped[int] = mapped_column(Integer)
    air_temp: Mapped[float | None] = mapped_column(Float)
    track_temp: Mapped[float | None] = mapped_column(Float)
    humidity: Mapped[float | None] = mapped_column(Float)
    rainfall: Mapped[bool] = mapped_column(Boolean, default=False)
    wind_speed: Mapped[float | None] = mapped_column(Float)

    race: Mapped["Race"] = relationship(back_populates="weather_readings")