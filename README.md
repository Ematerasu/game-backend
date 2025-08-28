# GameBackend – Matchmaking Queue System

A production-ready backend skeleton for a **game-style matchmaking system**, inspired by League of Legends.  
Built with **FastAPI**, **Celery**, **Redis**, and **PostgreSQL**, including rating updates with **TrueSkill**, observability with **Prometheus**, and a load simulation script.

---

## Features

- **Player registration & authentication** (JWT implemented, for now not used).
- **Matchmaking queue** with multi-region support, queue per region.
- **TrueSkill rating updates** after match results.
- **Asynchronous worker** (Celery) for creating matches and processing results.
- **Prometheus metrics** from both API and worker.
- **Load simulation script** (`simulation.py`) to stress-test the system.
- **Docker Compose setup** for local development.
- **AWS-ready** architecture (can be migrated to ECS Fargate + RDS + ElastiCache + Secrets Manager).

---

## Architecture

```

Clients (SDK / curl / simulation)
|
v
FastAPI  <---> PostgreSQL
|
v
Redis (broker/results)
|
v
Celery Worker/Beat  ---> Prometheus (/metrics)

```

- **API:** FastAPI service with JWT + `x-api-key` auth.
- **Worker/Beat:** Celery jobs to match players and apply results.
- **Database:** PostgreSQL with SQLAlchemy models.
- **Metrics:** Exported in Prometheus format for Grafana dashboards.

---

## Quick Start

Requirements: Docker + Compose v2.

```bash
docker compose -f deploy/docker-compose.yml up -d --build
curl -fsS http://localhost:8080/healthz
````

Default services:

* `postgres` (database)
* `redis` (broker & results)
* `api` (FastAPI, port `8080`)
* `matcher-worker` (Celery worker)
* `matcher-beat` (Celery scheduler)
* `prometheus` (metrics scraping)

---

## API Endpoints (summary)

### Matchmaking

* `POST /matchmaking/queue` — enqueue a player.
* `GET /matchmaking/queue/{player_id}` — get queue status.
* `DELETE /matchmaking/queue/{player_id}` — remove player from queue.
* `GET /matchmaking/matches/latest` — list recent matches.
* `GET /matchmaking/match/{match_id}` — match details.
* `POST /matchmaking/match/{match_id}/result` — submit results.

### Players

* `POST /players/register` — register a new player (returns `player_id` + JWT token).
* `GET /players/player/{player_id}` — player profile.
* `GET /players/leaderboard` — leaderboard (based on `mu - 3*sigma`).

### Health

* `GET /healthz` — service health check.

---

## Authentication

* **Player endpoints**: `Authorization: Bearer <token>` (JWT returned at registration).
* **System endpoints**: require `x-api-key` header (value from environment).

---

## Configuration (Environment Variables)

* `DB_DSN` – PostgreSQL DSN (e.g. `postgresql+psycopg://postgres:postgres@postgres:5432/game`)
* `API_KEY` – API key for system actions
* `JWT_SECRET` – secret for JWT signing
* `CELERY_BROKER_URL` – Redis broker URL
* `CELERY_RESULT_BACKEND` – Redis backend URL
* `REGIONS` – list of regions (e.g. `EUW,EUNE,NA,KR`)
* `MATCH_BETA` – matchmaking parameter (controls tolerance for rating differences)
* `METRICS_PORT` – Prometheus exporter port (worker)

---

## Simulation (Load Testing)

`simulation.py` can register players, enqueue them, and simulate thousands of matches.

```bash
export API_URL=http://localhost:8080
export API_KEY=dev
python simulation/simulation.py
```

Parameters inside the script:

* `N_PLAYERS` — number of players to register.
* `GAMES_PER_PLAYER` — number of games per player.
* `CONCURRENCY` — concurrency of HTTP requests.
* `REGIONS` — list of regions.

---

## Metrics & Observability

* Both API and Worker expose Prometheus metrics (`/metrics`).
* Example dashboards:

  * Queue depth per region
  * Matches created per tick
  * Tick latency
  * Rating update errors

Prometheus config is in `deploy/prometheus.yml`.

---

## Matchmaking Algorithm (simplified)

1. Collect players from a queue (per region).
2. Group into candidate pools (4 players).
3. Evaluate possible splits into teams.
4. Compute cost = rating difference + β \* rating uncertainty.
5. Pick the best split, record the match, dequeue players.
6. After match result: update ratings with TrueSkill.

---

## Development & Testing

* **Unit/Integration Tests** (require database):

  ```bash
  pip install -r services/api/requirements.txt
  pytest -q services/api/tests
  ```

* **End-to-End Tests**:

  ```bash
  docker compose -f deploy/docker-compose.test.yml up -d --build
  pytest -q tests/e2e
  docker compose -f deploy/docker-compose.test.yml down -v
  ```

* **Simulation**: see above.

---

## AWS Readiness

This project is cloud-agnostic and can be deployed to AWS:

* **ECS Fargate** — run API + Worker as services.
* **RDS** — managed PostgreSQL.
* **ElastiCache** — managed Redis.
* **Secrets Manager** — for API keys and JWT secrets.

An `infra/terraform/` directory can be added for Infrastructure as Code (VPC, ECS, RDS, Redis).

---

## Roadmap

* Player parties & constraints in matchmaking.
* Leaderboard pagination & filters.
* Rating decay for inactive players.
* WebSocket for client apps, so that information about match created is propagated to players matched
* Terraform AWS definitions (optional).

---

## License

MIT.
