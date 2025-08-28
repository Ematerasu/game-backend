import os

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from .routes import matchmaking, players
from .db import ensure_schema, engine

DB_DSN = os.getenv("DB_DSN", "postgresql+psycopg://postgres:postgres@postgres:5432/game")

app = FastAPI(title="Game Backend API")
instr = Instrumentator().instrument(app)

@app.on_event("startup")
def _startup():
    # Ensure DB schema exists (with retries) before serving requests
    ensure_schema()
    instr.add(
        lambda instrumentator:
            instrumentator.add(
                name="queue_depth",
                description="Number of players currently enqueued, by region",
                labels={"region": lambda req, resp: "ALL"},
                handler=lambda req, resp: _queue_depth_handler(),
            )
    )
    instr.expose(app)

def _queue_depth_handler():
    try:
        with engine.begin() as conn:
            c = conn.execute(text("SELECT COUNT(*) FROM queue")).scalar_one()
            return float(c)
    except Exception:
        return 0.0  # fail-safe

@app.get("/healthz")
def health():
    return {"status": "ok"}

app.include_router(matchmaking.router)
app.include_router(players.router)
