# RaceOps — Phase 0 Planning Doc

## 1. Product Requirements Document (PRD)

### Problem
Race engineers make pit-stop decisions under uncertainty — tire degradation, safety car timing, and rival strategy all interact nonlinearly. Most public F1 content shows *what happened*, not *what the range of good decisions looked like at the time*. RaceOps recreates that decision problem: given a race state, what's the probability distribution over outcomes for each strategy option?

### Target users (portfolio framing)
- Primary: hiring engineers/recruiters evaluating this as a systems + ML project
- Secondary (in-product framing): a fictional "race strategist" persona who wants pit recommendations mid-race

### Goals (MVP)
1. Ingest and normalize real F1 race data (2021–present) into Postgres
2. Simulate a race from any lap using Monte Carlo methods, randomizing tire deg, pit-stop duration, safety car occurrence, and overtake success
3. Recommend pit timing with probability-weighted outcomes (Pit Now / +1 / +2 laps)
4. Support both a deterministic and a trained (ML) tire degradation model behind a common interface, with a documented accuracy comparison
5. Present results through a clean dashboard: current race state, strategy simulator, results, race explorer

### Non-goals (explicitly out of MVP scope)
- Live/real-time race ingestion or WebSockets
- Redis caching, background job queues
- Multi-service deployment, Kubernetes, Ray-based parallelism
- Natural-language / LLM race engineer interface
- Full-season coverage on day one (start with a curated set of races)

### Success criteria
- A recruiter can understand the product in under 2 minutes from the dashboard
- You can defend architecture, data modeling, algorithm choice (Monte Carlo), performance, testing, and trade-offs for 30–45 min in an interview
- The ML backtest artifact shows the learned tire model's calibration against real outcomes
- Deployable locally via `docker-compose up`

### Scope for v1 data
- Seasons: 2021–2024 (hybrid era, consistent regs, good FastF1 telemetry coverage)
- Start with a curated subset: ~5–8 races with varied characteristics (high degradation circuit, safety-car-prone circuit, low-deg circuit, wet race) rather than the full calendar — enough variety for the sim to be interesting without a huge ingestion job

---

## 2. Architecture (MVP — no Redis, no background jobs)

```
┌─────────────────────┐
│   Next.js Dashboard  │
└──────────┬───────────┘
           │ REST (JSON)
┌──────────▼───────────┐
│     FastAPI App       │
│  ┌─────────────────┐  │
│  │  api/            │  │  routers: races, drivers, laps, strategy
│  │  services/       │  │  race_state, strategy_service
│  │  simulation/      │  │  monte_carlo, tire_models (deterministic + ML)
│  │  ingestion/       │  │  fastf1 pull + normalize scripts
│  │  models/          │  │  SQLAlchemy models + Pydantic schemas
│  └─────────────────┘  │
└──────────┬───────────┘
           │ SQLAlchemy
┌──────────▼───────────┐
│      PostgreSQL        │
└─────────────────────┘
```

One deployable app, organized so `simulation/` or `ingestion/` could later split into their own services — but they don't need to yet.

---

## 3. Database Schema (draft)

```
drivers
  id, driver_ref, given_name, family_name, nationality

constructors
  id, constructor_ref, name, nationality

circuits
  id, circuit_ref, name, country, lat, lng

races
  id, season, round, circuit_id (FK), race_date, name

race_results
  id, race_id (FK), driver_id (FK), constructor_id (FK),
  grid_position, finish_position, status, points

laps
  id, race_id (FK), driver_id (FK), lap_number, lap_time_ms,
  position, sector_1_ms, sector_2_ms, sector_3_ms, compound, tyre_life

stints
  id, race_id (FK), driver_id (FK), stint_number,
  compound, lap_start, lap_end, tyre_life_start

pit_stops
  id, race_id (FK), driver_id (FK), lap_number,
  duration_ms, stop_number

weather
  id, race_id (FK), lap_number, air_temp, track_temp,
  humidity, rainfall (bool), wind_speed
```

Notes:
- `laps.compound` + `tyre_life` gives you the raw signal for both the deterministic curve and the trained model's training set
- `weather` at lap granularity (FastF1 provides this) lets you condition strategy on conditions later without a schema change

---

## 4. API Contract (sketch)

```
GET  /races                        list races (filter by season)
GET  /races/{race_id}              race detail
GET  /races/{race_id}/laps         all laps (filter by driver)
GET  /races/{race_id}/state?lap=N  race state snapshot at lap N (Phase 3 model)

POST /strategy/simulate
  body: { race_id, driver_id, lap, candidate_pit_laps: [N, N+1, N+2], model: "deterministic"|"ml" }
  returns: { race_id, driver_id, results: [{ pit_lap, win_prob, avg_finish_pos, p10, p90 }] }

GET  /strategy/backtest/{race_id}  compare model recommendation vs actual outcome (Phase 7)
```

Full OpenAPI spec gets generated automatically from FastAPI — this sketch is just to lock the shapes before building.

---

## 5. Milestones (GitHub Project Board columns → issues)

- [ ] **M0 — Planning**: this doc reviewed, season/race list finalized, repo scaffolded
- [ ] **M1 — Spike**: single-race FastF1 pull → DataFrame → naive Monte Carlo → terminal output
- [ ] **M2 — Data layer**: ingestion scripts for all 5–8 races, schema migrated (Alembic), `/races` `/laps` endpoints live
- [ ] **M3 — Race state engine**: race-state Pydantic model, snapshot endpoint
- [ ] **M4 — Physics engine (deterministic)**: tire deg, fuel burn, pit loss, lap time, traffic models
- [ ] **M5 — ML tire model**: trained model on real degradation data, swappable behind same interface, initial accuracy check
- [ ] **M6 — Monte Carlo engine**: full sim loop, runs with both tire models, `/strategy/simulate` live
- [ ] **M7 — Dashboard**: 4 pages (Dashboard, Simulator, Results, Race Explorer)
- [ ] **M8 — Polish**: tests, CI, logging, API docs, backtest notebook + endpoint

---

## 6. Open decisions to finalize before M0 is "done"
- [x] Exact races for v1 — finalized after telemetry verification (see `verify_telemetry.py`):
  - 2023 Bahrain GP — high degradation
  - 2023 Azerbaijan GP (Baku) — low degradation
  - 2023 Singapore GP — safety-car-prone
  - 2021 Turkish GP — wet race
  - 2023 Canadian GP — mixed/wet conditions
  - (Rejected: 2022 British GP — marginal accuracy/telemetry scores; 2022 Japanese GP and 2024 São Paulo GP — both fell below the accurate-lap threshold, largely due to red-flag-shortened race distance and heavy SC/VSC periods reducing timing-loop accuracy)
- [x] Confirm FastF1 telemetry completeness for the chosen races — all 5 pass accuracy (≥0.85 accurate-lap fraction, except Bahrain at 0.866 and Canada at 0.856, both above threshold) and telemetry coverage (≥0.90) thresholds