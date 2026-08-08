# M2 - Data Layer: Summary & Decisions

## What was built
A complete, working data layer for F1RaceOps, taken end to end:
Postgres (Docker) → SQLAlchemy models → Alembic migrations → FastF1
ingestion → live FastAPI endpoints, all validated against the 5 finalized
v1 races.

- **Schema**: 9 tables (`drivers`, `constructors`, `circuits`, `races`,
  `race_results`, `laps`, `stints`, `pit_stops`, `weather`), defined as
  SQLAlchemy 2.0 models and applied via a single Alembic migration.
- **Ingestion**: `backend/ingestion/load_race.py` pulls one race from
  FastF1 and normalizes it into all 9 tables; `scripts/ingest_all_races.py`
  runs it across the full v1 set. Re-running is safe — existing rows for a
  race are cleared and replaced rather than duplicated.
- **API**: `GET /races`, `GET /races/{id}`, `GET /races/{id}/laps` (plus
  `/health`), each backed by real ingested data.

## Key design decisions

**Postgres via Docker (`postgres:16-alpine`), not a native install.**
Zero local version drift, and it's the direction the project was headed
anyway once the full stack gets containerized. Alpine specifically for a
smaller image with no real downside for a project with no exotic
extensions. (See also ADR 0001.)

**`.env` as the single source of truth for config**, read by
`docker-compose.yml`, Alembic's `env.py`, and the app itself — rather than
duplicating credentials across multiple config files that could drift
apart.

**Lap times stored as integer milliseconds, not float seconds.** Avoids
floating-point rounding drift across a large number of rows; converted to
seconds only in the API response layer, where it's more ergonomic.

**`is_accurate` / `is_generated` stored directly on `Lap`.** Not part of
the original Phase 0 schema sketch — added because the entire
`verify_telemetry.py` workflow exists to check exactly these two FastF1
flags. Storing them per-row means any future query can filter on data
quality directly in SQL instead of re-deriving it from FastF1 every time.

**Unique constraints on natural keys** (e.g. `race+driver+lap_number`,
`season+round`) make ingestion idempotent — re-running against an
already-loaded race fails loudly on exact duplicates rather than silently
doubling rows. Combined with the ingestion module explicitly clearing a
race's existing rows before re-loading it, this makes the whole pipeline
safe to re-run.

**Stints are aggregated, not independently derived.** FastF1 already
tags each lap with a `Stint` number — the ingestion module groups laps by
`(driver, stint)` and summarizes (min/max lap, dominant compound) rather
than reconstructing stint boundaries from scratch.

**Pit stops are inferred from `PitInTime`/`PitOutTime`** — FastF1 doesn't
provide a dedicated pit-stop table, so a stop is identified as the gap
between an in-lap's `PitInTime` and the following out-lap's `PitOutTime`.

**Weather readings are bucketed to one row per lap, not per raw
timestamp.** FastF1's weather data is time-indexed at roughly one reading
per minute, which doesn't line up 1:1 with laps. Multiple readings that
map to the same approximate lap are averaged into a single row — both to
match the `weather` table's `(race_id, lap_number)` uniqueness and because
lap-level granularity is what queries will actually want.

**Upgraded the project from Python 3.9 to 3.12** mid-build, after 3.9's
union-type syntax (`str | None`) turned out to be a runtime error on 3.9
(it needs 3.10+). Also a good opportunity to move off a Python version
that's already past its official end-of-life.

## Verification results
- Row counts across all 5 races landed in the expected range (roughly
  1,000–1,300 laps per race depending on race length and retirements),
  consistent with the totals `verify_telemetry.py` reported during race
  selection.
- Spot-checked the 2023 Singapore GP's driver count (19, not 20) against
  `race_results.status` and confirmed it correctly reflects Lance
  Stroll's real withdrawal from that race — not a data-loss bug. The
  ingestion pipeline handled this edge case (a driver present in results
  but with zero laps) correctly without any special-case code.

## What's next
Phase 3 (M3) — the race state engine: a Pydantic model representing "what
does the race look like at lap N" (position, gaps, tire age, weather),
built directly on top of this data layer.