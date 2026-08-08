# ADR 0001: Use PostgreSQL from Day One

**Status:** Accepted

## Context
The Phase 1 data layer needs a database. The alternative considered was starting
with SQLite for the initial spike/ingestion work (zero setup friction, no
Docker dependency) and migrating to PostgreSQL once the app was containerized.

## Decision
Use PostgreSQL from the start, including for the Phase 1 spike, rather than
starting on SQLite and migrating later.

## Consequences
- Slightly more setup friction at the very start (need Postgres running
  locally or via Docker before writing the first ingestion script).
- Avoids a migration step later — schema, Alembic migrations, and query
  patterns (e.g. JSON columns, window functions used in lap analysis) are
  written once against the database the project will actually ship with.
- More representative of a production environment, which matters for the
  "how would this scale" conversation in interviews — no need to caveat
  "the reference implementation uses SQLite, but in production...".