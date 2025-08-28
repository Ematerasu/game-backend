import os, json
import uuid

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import text

from ..security import create_access_token
from ..db import engine


router = APIRouter(prefix="/players", tags=["players"])

DB_DSN = os.getenv("DB_DSN", "postgresql+psycopg://postgres:postgres@localhost:5432/game")

class RegisterIn(BaseModel):
    username: str
    region: str = "EUW"


@router.get("/player/{player_id}")
def get_player(player_id: str):
    with engine.begin() as conn:
        player = conn.execute(
            text("SELECT player_id, region, mu, sigma, last_active FROM players WHERE player_id = :pid"),
            {"pid": player_id}
        ).mappings().first()

        if not player:
            raise HTTPException(status_code=404, detail=f"Player {player_id} not found!")

        return {
            "player_id": player["player_id"],
            "mu": player["mu"],
            "sigma": player["sigma"],
            "conservative_rating": player["mu"] - 3.0 * player["sigma"],
            "last_active": player["last_active"].isoformat() if player["last_active"] else None,
        }

@router.get("/leaderboard")
def leaderboard(limit: int = 20):
    if limit < 1 or limit > 100:
        limit = 20
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT username, mu, sigma, (mu - 3*sigma) AS cr
                FROM players
                ORDER BY cr DESC
                LIMIT :lim
            """),
            {"lim": limit},
        ).mappings().all()

    return [
        {
            "rank": i+1,
            "username": r["username"],
            "mu": r["mu"],
            "sigma": r["sigma"],
            "conservative_rating": r["cr"],
        }
        for i, r in enumerate(rows)
    ]

# Very simplified for this project purposes,
# I wanna focus on handling large amounts of users and this approach makes it easy to spawn tons of them
# We use idempotency key to avoid retries with different playerID
@router.post("/register")
def register(body: RegisterIn, x_idempotency_key: str | None = Header(None)):
    player_id = (
            str(uuid.uuid5(uuid.UUID("11111111-1111-1111-1111-111111111111"), x_idempotency_key))
            if x_idempotency_key
            else str(uuid.uuid4())
        )
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO players (player_id, username, region, mu, sigma, last_active)
                    VALUES (:pid, :username, :reg, 25.0, 8.333, NOW() AT TIME ZONE 'UTC')
                    ON CONFLICT (player_id) DO NOTHING"""),
            {"pid": player_id, "username": body.username, "reg": body.region},
        )
    token = create_access_token(sub=player_id, roles=["player"])
    return {"player_id": player_id, "access_token": token, "token_type": "bearer"}
