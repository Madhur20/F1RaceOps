# ADR 0002: Defer Redis and Background Job Queues

**Status:** Accepted

## Context

The original architecture sketch included Redis as a caching layer alongside
Postgres. For a single-user, on-demand simulation tool with no live/real-time
ingestion in the MVP, there is no caching or async-job problem yet to solve.

## Decision

Do not add Redis, Celery, or any background job queue to the MVP (Phases 0–7).
Revisit only if a concrete problem emerges that they solve — e.g. repeated
re-simulation of the same race state, or live timing ingestion in a later
version.

## Consequences

- Simpler local dev setup (one fewer service in docker-compose for the MVP).
- Every piece of infrastructure in the running system is there because it's
  load-bearing, not because it "looks production-ready" — this is a more
  defensible answer to "why did you add X" in an interview than infra added
  preemptively for the resume.
- Live race replay, WebSockets, and real-time ingestion (planned for v2) will
  likely require revisiting this decision — noted as a known follow-up, not
  a rejection of Redis outright.
