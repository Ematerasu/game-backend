from typing import Literal, Optional
import os

from celery import Celery
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app import db
from app.services.matchmaking_service import (
    enqueue_player, dequeue_player, get_queue_status,
    get_match_by_id, list_latest_matches, report_result_with_task
)
from app.security import check_api_key


CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
celery_app = Celery("api", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

router = APIRouter(prefix="/matchmaking", tags=["matchmaking"])

# --- Schemas ---
class EnqueueIn(BaseModel):
    player_id: str
    constraints: dict | None = None

class QueueStatusOut(BaseModel):
    player_id: str
    enqueued: bool
    region: Optional[Literal["EUW","EUNE","NA","CHN","JPN","KR","OCE","BR","LAS","LAN"]] = None
    enqueued_at: Optional[str] = None

class ResultIn(BaseModel):
    winner_team: Literal["teamA", "teamB"]

# --- Routes ---
@router.post("/queue")
def enqueue(body: EnqueueIn, _: None = Depends(check_api_key)):
    with db.engine.begin() as conn:
        result = enqueue_player(conn, body.player_id, body.constraints)
    return result

@router.delete("/queue/{player_id}")
def dequeue(player_id: str, _: None = Depends(check_api_key)):
    with db.engine.begin() as conn:
        return dequeue_player(conn, player_id)

@router.get("/queue/{player_id}", response_model=QueueStatusOut)
def queue_status(player_id: str):
    with db.engine.begin() as conn:
        return get_queue_status(conn, player_id)

@router.get("/match/{match_id}")
def get_match(match_id: str):
    with db.engine.begin() as conn:
        return get_match_by_id(conn, match_id)

@router.get("/matches/latest")
def latest_matches(limit: int = Query(5, ge=1, le=50)):
    with db.engine.begin() as conn:
        return list_latest_matches(conn, limit)

@router.post("/match/{match_id}/result")
def report_result(match_id: str, body: ResultIn, _: None = Depends(check_api_key)):
    def _send_task(name: str, args: list) -> None:
        celery_app.send_task(name, args=args)
    with db.engine.begin() as conn:
        return report_result_with_task(conn, match_id, body.winner_team, _send_task)
