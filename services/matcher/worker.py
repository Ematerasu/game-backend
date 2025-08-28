import os, uuid, json
from datetime import datetime, timezone

from celery import Celery
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from trueskill import Rating, rate

celery_app = Celery(
    "matcher",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
)

# Beat schedule: call match_tick every 0.2s
celery_app.conf.beat_schedule = {
    "match-tick": {"task": "matcher.worker.match_tick", "schedule": 0.2}
}

DB_DSN = os.getenv("DB_DSN", "postgresql+psycopg://postgres:postgres@postgres:5432/game")
engine = create_engine(DB_DSN, pool_pre_ping=True)

REGIONS = os.getenv("REGIONS", "EUW").split(",")
BETA = float(os.getenv("MATCH_BETA", "0.1"))

def _score_split(teamA, teamB):
    muA = sum(p["mu"] for p in teamA) / len(teamA)
    muB = sum(p["mu"] for p in teamB) / len(teamB)
    sigmaA = sum(p["sigma"] for p in teamA) / len(teamA)
    sigmaB = sum(p["sigma"] for p in teamB) / len(teamB)
    diff = abs(muA - muB)
    return diff + BETA * (sigmaA + sigmaB)

def _best_split(players4):
    # players4: list[{"player_id","mu","sigma"}] length==4
    p = players4
    splits = [
        ([p[0], p[1]], [p[2], p[3]]),
        ([p[0], p[2]], [p[1], p[3]]),
        ([p[0], p[3]], [p[1], p[2]]),
    ]
    scored = [(s, _score_split(*s)) for s in splits]
    (teamA, teamB), score = min(scored, key=lambda x: x[1])
    quality = 1.0 / (1.0 + score)
    return teamA, teamB, quality

def _fetch_4_locked(conn, region: str):
    # Lock the 4 oldest for this region; skip rows locked by other worker
    rows = conn.execute(
        text("""
        SELECT player_id, mu, sigma, enqueued_at
        FROM queue
        WHERE region = :r
        ORDER BY enqueued_at
        FOR UPDATE SKIP LOCKED
        LIMIT 4
        """),
        {"r": region},
    ).mappings().all()
    return rows

def _fetch_match(conn, match_id: str):
    return conn.execute(
        text("SELECT match_id, players, region, status FROM matches WHERE match_id = :mid"),
        {"mid": match_id},
    ).mappings().first()

def _players_by_id(conn, ids):
    rows = conn.execute(
        text("SELECT player_id, mu, sigma FROM players WHERE player_id = ANY(:ids)"),
        {"ids": ids},
    ).mappings().all()
    return {r["player_id"]: r for r in rows}

def _delete_from_queue(conn, player_ids):
    conn.execute(
        text("DELETE FROM queue WHERE player_id = ANY(:pids)"),
        {"pids": player_ids},
    )

def _insert_match(conn, match_id, region, teamA, teamB, quality):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        text("""
        INSERT INTO matches (match_id, players, created_at, region, quality, status)
        VALUES (:mid, :players, :created_at, :region, :quality, 'pending')
        """),
        {
            "mid": match_id,
            "players": json.dumps({
                "teamA": teamA,
                "teamB": teamB,
            }),
            "created_at": now,
            "region": region,
            "quality": quality,
        },
    )

@celery_app.task(name="matcher.worker.match_tick")
def match_tick():
    made = 0
    try:
        with engine.begin() as conn:
            for region in REGIONS:
                while True:
                    rows = _fetch_4_locked(conn, region)
                    if len(rows) < 4:
                        break
                    players4 = [{"player_id": r["player_id"], "mu": r["mu"], "sigma": r["sigma"]} for r in rows]
                    teamA, teamB, quality = _best_split(players4)
                    match_id = str(uuid.uuid4())
                    _insert_match(conn, match_id, region, teamA, teamB, quality)
                    _delete_from_queue(conn, [p["player_id"] for p in players4])
                    made += 1
    except OperationalError as e:
        # DB hiccup; let beat call next round
        return {"status": "db-error", "err": str(e)}
    return {"status": "ok", "matches_created": made}


@celery_app.task(name="matcher.worker.apply_result")
def apply_result(match_id: str, winner_team: str):
    # winner_team in {"teamA", "teamB"}
    try:
        with engine.begin() as conn:
            m = _fetch_match(conn, match_id)
            if not m:
                return {"status": "no-match", "match_id": match_id}
            # if already finished, skip
            if m["status"] == "finished":
                return {"status": "already-finished", "match_id": match_id}

            players = m["players"]  # JSON from DB (SQLAlchemy returns dict)
            teamA = players["teamA"]
            teamB = players["teamB"]

            idsA = [p["player_id"] for p in teamA]
            idsB = [p["player_id"] for p in teamB]
            all_ids = idsA + idsB
            current = _players_by_id(conn, all_ids)

            teamA_r = [Rating(mu=current[pid]["mu"], sigma=current[pid]["sigma"]) for pid in idsA]
            teamB_r = [Rating(mu=current[pid]["mu"], sigma=current[pid]["sigma"]) for pid in idsB]

            ranks = [0, 1] if winner_team == "teamA" else [1, 0]
            (newA, newB) = rate([teamA_r, teamB_r], ranks=ranks)

            for pid, r in zip(idsA, newA):
                conn.execute(
                    text("UPDATE players SET mu=:mu, sigma=:sigma, last_active=NOW() AT TIME ZONE 'UTC' WHERE player_id=:pid"),
                    {"mu": float(r.mu), "sigma": float(r.sigma), "pid": pid},
                )
            for pid, r in zip(idsB, newB):
                conn.execute(
                    text("UPDATE players SET mu=:mu, sigma=:sigma, last_active=NOW() AT TIME ZONE 'UTC' WHERE player_id=:pid"),
                    {"mu": float(r.mu), "sigma": float(r.sigma), "pid": pid},
                )

            conn.execute(
                text("UPDATE matches SET status='finished' WHERE match_id=:mid"),
                {"mid": match_id},
            )
            conn.execute(
                text("""
                INSERT INTO results (match_id, winner_team, reported_at)
                VALUES (:mid, :wt, NOW() AT TIME ZONE 'UTC')
                ON CONFLICT (match_id) DO NOTHING
                """),
                {"mid": match_id, "wt": winner_team},
            )

        return {"status": "ok", "match_id": match_id, "winner": winner_team}
    except Exception as e:
        return {"status": "error", "match_id": match_id, "err": str(e)}
