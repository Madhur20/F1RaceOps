# F1RaceOps

I built this because I wanted a portfolio project that actually looks like real engineering work, not just working code, but the planning that came before it and the debugging that happened along the way. It's a race strategy platform for Formula 1: real telemetry data, a Postgres/FastAPI backend, and a Monte Carlo simulator that recommends pit strategies based on actual win probability instead of gut feel.

**Where things stand:** the data pipeline, race state engine, tire degradation model, and the full Monte Carlo strategy simulator are all built, tested, and live behind a real API, including multi-stop strategies with a different tire compound per stint. What's left is mostly polish: a dashboard, a proper test suite, and CI. I've tried to keep this README honest about what's actually working versus what's still on the list, so check the [roadmap](#roadmap) at the bottom rather than assuming everything here is finished.

## What this is

Race engineers have to decide when to pit under real uncertainty, tire wear, safety car timing, what the other teams are doing. This project recreates that decision: given a real race at any lap, it simulates thousands of possible outcomes for different pit strategies and compares them on actual win probability rather than intuition.

## Why I documented this so heavily

Most portfolio projects just show the finished code. I wanted this one to also show the process, since that's closer to what the actual job looks like. Every milestone in [`docs/`](./docs) has two files: a summary of what got built and why, and a debugging log of what went wrong and how I tracked it down. A few of my favorites:

- **A Monte Carlo comparison that was quietly meaningless.** An early version compared pit strategies using random numbers that weren't properly paired across strategies, so the "which strategy wins" result was basically noise dressed up as an answer. See [`docs/spike-debugging-log.md`](./docs/spike-debugging-log.md).
- **A fix that worked but wasn't actually right.** A bug fix for missing race-state data technically solved the symptom, but re-testing against real data showed the whole approach (summing lap times to get elapsed race time) was fragile in a way that would keep causing problems. See [`docs/m3-debugging-log.md`](./docs/m3-debugging-log.md).
- **A tire model that thought tires got faster with age.** My first degradation fit showed HARD tires wearing faster than SOFT, backwards. Turned out fuel burn-off and circuit baseline pace were both confounding the result. See [`docs/m4-degradation-model.md`](./docs/m4-degradation-model.md).
- **A strategy engine that recommended wet tires for a bone-dry race.** The multi-stop search once confidently suggested INTERMEDIATE tires at Bahrain, a race with zero rain. The model wasn't broken; it was just missing a constraint I hadn't thought to add (it had no idea wet tires are a different tool, not just a slower-degrading option). See [`docs/m6-debugging-log.md`](./docs/m6-debugging-log.md).

## Architecture

```
        React/Next.js Dashboard  (planned, next up)
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

It's one deployable service, organized so each piece could split into its own service later without a rewrite, I didn't want to over-engineer this into microservices before there was any real reason to. The reasoning behind that and a few other architectural calls is in [`docs/decisions/`](./docs/decisions).

## Tech stack

**Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL, Pydantic

**Data / ML:** FastF1, pandas, NumPy, scikit-learn

**Infra:** Docker Compose (Postgres), pytest _(planned)_, GitHub Actions _(planned)_

## What's implemented today

- **Data pipeline**, pulls real F1 telemetry (laps, stints, pit stops, weather, results) from [FastF1](https://github.com/theOehrly/Fast-F1) for 5 races spanning 2021–2023. I picked them deliberately to cover a high-degradation circuit, a low-degradation one, a safety-car-prone one, and a wet race, each verified against FastF1's own data-quality flags before I trusted it.
- **Live API**, `GET /races`, `GET /races/{id}`, `GET /races/{id}/laps`, `GET /races/{id}/state?lap=N` (a full race snapshot: positions, gaps, tire age, weather), all backed by real ingested data.
- **Tire degradation model**, a per-compound degradation rate fit from real lap data, using a regression that separates the tire-aging effect from confounding fuel-burn and circuit-baseline effects. Validated result: degradation increases in the order you'd actually expect on track, INTERMEDIATE < HARD < MEDIUM < SOFT.
- **ML degradation model**, a gradient-boosted alternative to the model above, trained and validated on held-out real laps (0.73s mean absolute error), included mainly to give this project a real "trained and benchmarked a model" story alongside the statistical one.
- **Monte Carlo strategy simulator, live**, `POST /strategy/simulate` runs thousands of simulated outcomes per candidate strategy using common random numbers for a statistically valid comparison, including a safety-car-reactive strategy and multi-stop strategies with a different compound per stint.

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

Try the strategy simulator once it's running:

```bash
curl -X POST http://localhost:8000/strategy/simulate -H "Content-Type: application/json" -d '{
  "race_id": 1, "driver_code": "VER", "current_lap": 20, "current_tyre_age": 15, "compound": "MEDIUM"
}'
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

- [x] **M0**, Planning: PRD, architecture, schema, API contract
- [x] **M1**, Spike: prove the core Monte Carlo idea works on real data
- [x] **M2**, Data layer: ingestion + schema + live API
- [x] **M3**, Race state engine
- [x] **M4**, Physics/strategy engine: degradation, pit-loss, and fuel models, all real
- [x] **M5**, ML tire model, trained and validated against the deterministic version
- [x] **M6**, Monte Carlo engine live at `/strategy/simulate`, including multi-stop strategies
- [ ] **M7**, Dashboard (Next.js)
- [ ] **M8**, Testing, CI/CD, structured logging, model evaluation notebook

Full detail on every milestone is in [`docs/`](./docs).
