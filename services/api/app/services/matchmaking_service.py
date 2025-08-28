from __future__ import annotations
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Literal

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import queue, matches, results

Region = Literal["EUW","EUNE","NA","CHN","JPN","KR","OCE","BR","LAS","LAN"]

def enqueue_player(conn, player_id: str, constraints: dict | None):
    now = datetime.now(timezone.utc)

    p = conn.execute(
        text("SELECT player_id, region, mu, sigma FROM players WHERE player_id=:pid"),
        {"pid": player_id}
    ).mappings().first()
    if not p:
        raise HTTPException(status_code=404, detail="player not registered")

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    q_up = pg_insert(queue).values(
        player_id=p["player_id"],
        enqueued_at=now,
        region=p["region"],
        mu=p["mu"],
        sigma=p["sigma"],
        constraints=constraints,
    ).on_conflict_do_update(
        index_elements=[queue.c.player_id],
        set_={
            "enqueued_at": now,
            "region": p["region"],
            "mu": p["mu"],
            "sigma": p["sigma"],
            "constraints": constraints,
        },
    )
    conn.execute(q_up)
    return {"status": "enqueued", "player_id": player_id, "region": p["region"]}

def dequeue_player(conn: Connection, player_id: str) -> Dict:
    res = conn.execute(queue.delete().where(queue.c.player_id == player_id))
    return {"status": "dequeued" if res.rowcount else "not_found", "player_id": player_id}

def get_queue_status(conn: Connection, player_id: str) -> Dict:
    row = conn.execute(queue.select().where(queue.c.player_id == player_id)).mappings().first()
    if not row:
        return {"player_id": player_id, "enqueued": False}
    return {
        "player_id": player_id,
        "enqueued": True,
        "region": row["region"],
        "enqueued_at": row["enqueued_at"].isoformat() if row["enqueued_at"] else None,
    }

def get_match_by_id(conn: Connection, match_id: str) -> Dict:
    m = conn.execute(matches.select().where(matches.c.match_id == match_id)).mappings().first()
    if not m:
        raise HTTPException(status_code=404, detail="match not found")
    return {
        "match_id": m["match_id"],
        "players": m["players"],
        "region": m["region"],
        "quality": m["quality"],
        "status": m["status"],
        "created_at": m["created_at"].isoformat() if m["created_at"] else None,
    }

def list_latest_matches(conn: Connection, limit: int = 5) -> List[Dict]:
    rows = conn.execute(
        matches.select().order_by(matches.c.created_at.desc()).limit(limit)
    ).mappings().all()
    return [
        {
            "match_id": r["match_id"],
            "players": r["players"],
            "region": r["region"],
            "quality": r["quality"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]

def report_result_db(conn: Connection, match_id: str, winner_team: Literal["teamA","teamB"]) -> Dict:
    now = datetime.now(timezone.utc)
    m = conn.execute(matches.select().where(matches.c.match_id == match_id)).mappings().first()
    if not m:
        raise HTTPException(status_code=404, detail="match not found")

    conn.execute(
        pg_insert(results).values(
            match_id=match_id,
            winner_team=winner_team,
            reported_at=now,
        ).on_conflict_do_nothing()
    )
    conn.execute(matches.update().where(matches.c.match_id == match_id).values(status="reporting"))
    return {"status": "queued", "match_id": match_id, "winner_team": winner_team}

def report_result_with_task(
    conn: Connection,
    match_id: str,
    winner_team: Literal["teamA","teamB"],
    send_task: Callable[[str, list], None],
) -> Dict:
    out = report_result_db(conn, match_id, winner_team)
    send_task("matcher.worker.apply_result", [match_id, winner_team])
    return out
