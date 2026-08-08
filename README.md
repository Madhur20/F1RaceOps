# F1RaceOps

A production-inspired F1 race strategy platform: real telemetry ingestion,
a Postgres/FastAPI backend, and a Monte Carlo pit-strategy simulation
engine, built the way a small engineering team would — design docs and
architecture decisions before code, and a documented debugging trail
alongside every milestone.

**Status: actively in development.** The data layer, race state engine,
and a validated tire-degradation model are complete and tested against
real 2021–2023 F1 data. The full Monte Carlo strategy simulator (proven
out in an early prototype) is being integrated into the live API next.
See [Roadmap](#roadmap) below for exactly what's done vs. in progress —
nothing in this README describes a feature that doesn't actually work
today.

## What this is

Race engineers decide when to pit under real uncertainty: tire wear,
safety car timing, and rival strategy all interact nonlinearly. F1RaceOps
recreates that decision problem — given a real race's data at any lap,
simulate thousands of possible outcomes per pit-stop strategy and compare
them on actual win probability, not just intuition.

## Why this project is built the way it is

Most portfolio projects show finished code. This one also shows the
process — because that's closer to what the job actually is. Every
milestone in [`docs/`](./docs) has two documents: a summary of what was
built and why, and a debugging log of what went wrong and how it was
diagnosed. A few examples worth a look:

- **A statistically invalid Monte Carlo comparison, caught and fixed** —
  an early strategy comparison silently returned meaningless results
  because independent random number streams weren't properly paired
  across strategies. See [`docs/spike-debugging-log.md`](./docs/spike-debugging-log.md).
- **A regression that looked right but wasn't** — a first fix for a data
  bug technically worked, but re-testing against real data revealed the
  underlying approach (summing lap times) was fundamentally fragile, not
  just buggy in one spot. See [`docs/m3-debugging-log.md`](./docs/m3-debugging-log.md).
- **A tire-degradation model with a real, catchable confound** — the
  first fit showed tires appearing to speed up with age, because tyre-age
  and fuel burn-off are perfectly collinear within a single stint. Fixed
  by pooling across stints and adding per-race fixed effects. See
  [`docs/m4-degradation-model.md`](./docs/m4-degradation-model.md).

## Architecture

```
        React/Next.js Dashboard  (planned — Phase 5)
                    │
              REST (JSON)
                    │
             FastAPI Backend
    ┌───────────────┼────────────────┐
    │               │                │
  api/          services/       simulation/
 (routers)   (race state,      (Monte Carlo,
              queries)          tire models)
    │               │                │
    └───────────────┴────────────────┘
              SQLAlchemy ORM
                    │
                PostgreSQL
```

One deployable service, organized so each module could later split into
its own service without a rewrite — deliberately not over-engineered into
microservices for a project at this stage. See
[`docs/decisions/`](./docs/decisions) for the reasoning behind this and
other architectural calls.

## Tech stack

**Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL, Pydantic
**Data:** FastF1, pandas, NumPy (regression/statistics for the degradation model)
**Infra:** Docker Compose (Postgres), pytest _(planned)_, GitHub Actions _(planned)_

## What's implemented today

- **Data pipeline** — ingests real F1 telemetry (laps, stints, pit stops,
  weather, results) from [FastF1](https://github.com/theOehrly/Fast-F1)
  for 5 races spanning 2021–2023, chosen deliberately to cover
  high-degradation, low-degradation, safety-car-prone, and wet-race
  conditions, each verified against FastF1's own data-quality flags
  before inclusion.
- **Live API** — `GET /races`, `GET /races/{id}`, `GET /races/{id}/laps`,
  `GET /races/{id}/state?lap=N` (a full race-state snapshot: positions,
  gaps, tire age, weather), all backed by real ingested data.
- **Tire degradation model** — a per-compound degradation rate fit from
  real lap data, using a regression that separates the tire-aging effect
  from the confounding fuel-burn effect and controls for each circuit's
  own baseline pace. Validated result: degradation increases in the
  expected order (INTERMEDIATE < HARD < MEDIUM < SOFT).
- **Monte Carlo pit-strategy simulator (prototype)** — simulates thousands
  of race outcomes per candidate strategy, including a safety-car-reactive
  strategy, using common random numbers for statistically valid
  strategy-vs-strategy comparison. Currently a standalone script; being
  wired into the live API next.

## Getting started

```bash
git clone <this repo>
cd f1raceops

# Python env
python3.12 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Database
cp .env.example .env
docker compose up -d
alembic -c backend/alembic.ini upgrade head

# Load real race data (takes a few minutes on first run)
python scripts/ingest_all_races.py

# Run the API
uvicorn backend.main:app --reload --port 8000
# → http://localhost:8000/docs for interactive API docs
```

## Project structure

```
f1raceops/
├── backend/
│   ├── api/            # FastAPI routers
│   ├── models/          # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic request/response schemas
│   ├── services/          # race state queries
│   ├── simulation/         # tire models, Monte Carlo engine
│   ├── ingestion/          # FastF1 → Postgres pipeline
│   └── alembic/             # DB migrations
├── scripts/                  # ingestion runner, degradation model runner, etc.
├── docs/
│   ├── decisions/              # architecture decision records (ADRs)
│   └── *.md                     # per-milestone summaries + debugging logs
└── docker-compose.yml
```

## Roadmap

- [x] **M0** — Planning: PRD, architecture, schema, API contract
- [x] **M1** — Spike: prove the core Monte Carlo idea works on real data
- [x] **M2** — Data layer: ingestion + schema + live API
- [x] **M3** — Race state engine
- [x] **M4** — Physics/strategy engine: real degradation model _(in progress — pit-loss and fuel models next)_
- [ ] **M5** — ML tire model, trained on real lap data, compared against the deterministic version
- [ ] **M6** — Full Monte Carlo engine wired into a live `/strategy/simulate` endpoint
- [ ] **M7** — Dashboard (Next.js)
- [ ] **M8** — Testing, CI/CD, structured logging, model evaluation notebook

Full detail on each milestone is in [`docs/`](./docs).
