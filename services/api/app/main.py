import os

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram
from sqlalchemy import text

from .routes import matchmaking, players
from .db import ensure_schema, engine

DB_DSN = os.getenv("DB_DSN", "postgresql+psycopg://postgres:postgres@postgres:5432/game")

app = FastAPI(title="Game Backend API")
instr = Instrumentator().instrument(app)

ENQUEUE_REQS = Counter(
    "enqueue_requests_total", "Number of POST /matchmaking/queue calls"
)
ENQUEUE_LATENCY = Histogram(
    "enqueue_request_latency_seconds", "Latency of POST /matchmaking/queue"
)

@app.on_event("startup")
def _startup():
    ensure_schema()
    # --- queue depth per region ---
    def queue_depth_all_regions(_req, _resp):
        with engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT region, COUNT(*)::float AS cnt
                FROM queue
                GROUP BY region
            """)).mappings().all()
        for r in rows:
            instrumentator = Instrumentator() # dummy
        return float(sum(r["cnt"] for r in rows))

    instr.add(
        lambda instrumentator:
            instrumentator.add(
                name="queue_depth",
                description="Players enqueued (ALL + per region)",
                labels={
                    "region": lambda req, resp: "ALL",
                },
                handler=lambda req, resp: queue_depth_all_regions(req, resp),
            )
    )

    instr.add(
        lambda instrumentator:
            instrumentator.add(
                name="queue_depth_by_region",
                description="Players enqueued by region",
                labels={
                    "region": lambda req, resp: "PER_REGION",
                },
                handler=lambda req, resp: _queue_depth_by_region_handler(),
            )
    )

    instr.expose(app)

def _queue_depth_by_region_handler():
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT region, COUNT(*)::float AS cnt
                FROM queue
                GROUP BY region
            """)).mappings().all()
        return float(sum(r["cnt"] for r in rows))
    except Exception:
        return 0.0

@app.get("/healthz")
def health():
    return {"status": "ok"}

app.include_router(matchmaking.router)
app.include_router(players.router)
