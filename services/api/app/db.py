import os, time
from sqlalchemy import (
    create_engine, MetaData, Table, Column, String, Float, JSON, DateTime,
    UniqueConstraint, ForeignKey
)
from sqlalchemy.exc import OperationalError
from sqlalchemy import Enum as PgEnum

DB_DSN = os.getenv("DB_DSN", "postgresql+psycopg://postgres:postgres@postgres:5432/game")
engine = create_engine(DB_DSN, pool_pre_ping=True)
metadata = MetaData()

RegionsEnum = PgEnum(
    "EUW", "EUNE", "NA", "CHN", "JPN", "KR", "OCE", "BR", "LAS", "LAN",
    name="regions_enum",
    create_type=True,
)

players = Table(
    "players", metadata,
    Column("player_id", String, primary_key=True),
    Column("username", String, nullable=False),
    Column("region", RegionsEnum, nullable=False),
    Column("mu", Float, nullable=False),
    Column("sigma", Float, nullable=False),
    Column("last_active", DateTime(timezone=True), nullable=False),
)

queue = Table(
    "queue", metadata,
    Column("player_id", String, ForeignKey("players.player_id"), primary_key=True),
    Column("enqueued_at", DateTime(timezone=True), nullable=False),
    Column("region", RegionsEnum, nullable=False),
    Column("mu", Float, nullable=False),
    Column("sigma", Float, nullable=False),
    Column("constraints", JSON, nullable=True),
    UniqueConstraint("player_id", name="uq_queue_player"),
)

matches = Table(
    "matches", metadata,
    Column("match_id", String, primary_key=True),
    Column("players", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("region", RegionsEnum, nullable=False),
    Column("quality", Float, nullable=True),
    Column("status", String, nullable=False, default="pending"),
)

results = Table(
    "results", metadata,
    Column("match_id", String, primary_key=True),
    Column("winner_team", String, nullable=False),
    Column("reported_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("match_id", name="uq_results_match"),
)

def ensure_schema(max_tries: int = 30, sleep_s: float = 1.0):
    """Create tables with retry to handle DB cold start."""
    for attempt in range(1, max_tries + 1):
        try:
            with engine.begin() as conn:
                metadata.create_all(conn)
            return
        except OperationalError:
            if attempt == max_tries:
                raise
            time.sleep(sleep_s)
