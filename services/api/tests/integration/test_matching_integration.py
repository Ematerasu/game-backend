import pytest
from sqlalchemy import text

from .dbcase import DBTestCase
from app.services.matchmaking_service import (
    enqueue_player, dequeue_player, get_queue_status,
    get_match_by_id, list_latest_matches, report_result_db, report_result_with_task
)

@pytest.mark.integration
class TestMatchmaking(DBTestCase):

    def seed_player(self, pid="p1", name="Esdeath", region="EUW", mu=25.0, sigma=8.333):
        self.session.execute(text(
            "INSERT INTO players (player_id, username, region, mu, sigma, last_active) "
            "VALUES (:pid, :name, :region, :mu, :sigma, CURRENT_TIMESTAMP)"
        ), {"pid": pid, "name": name, "region": region, "mu": mu, "sigma": sigma})
        self.session.flush()

    def seed_match(self, mid="m1", region="EUW", status="created", quality=0.7, players=None):
        if players is None:
            players = ["p1","p2","p3","p4","p5","p6","p7","p8","p9","p10"]
        self.session.execute(text("""
            INSERT INTO matches (match_id, region, status, quality, players, created_at)
            VALUES (:mid, :region, :status, :quality, :players, CURRENT_TIMESTAMP)
        """), {"mid": mid, "region": region, "status": status, "quality": quality, "players": players})
        self.session.flush()

    def test_enqueue_status_dequeue(self):
        self.seed_player("p1")
        out = enqueue_player(self.connection, "p1", None)
        assert out["status"] == "enqueued" and out["player_id"] == "p1" and out["region"] == "EUW"

        st = get_queue_status(self.connection, "p1")
        assert st["enqueued"] is True and st["region"] == "EUW" and st["player_id"] == "p1"

        d = dequeue_player(self.connection, "p1")
        assert d["status"] in ("dequeued", "not_found") and d["player_id"] == "p1"

        st2 = get_queue_status(self.connection, "p1")
        assert st2["enqueued"] is False

    def test_get_match_and_latest(self):
        self.seed_match("m1", quality=0.3)
        self.seed_match("m2", quality=0.6)
        self.seed_match("m3", quality=0.9)

        m2 = get_match_by_id(self.connection, "m2")
        assert m2["match_id"] == "m2" and m2["status"] == "created"

        latest = list_latest_matches(self.connection, limit=2)
        assert len(latest) == 2
        assert latest[0]["match_id"] in {"m3","m2"}
        assert latest[0]["created_at"] is not None

    def test_report_result_db_and_task(self):
        self.seed_match("m10")
        sent = []

        def fake_send_task(name: str, args: list):
            sent.append((name, args))

        out = report_result_with_task(self.connection, "m10", "teamA", fake_send_task)
        assert out == {"status": "queued", "match_id": "m10", "winner_team": "teamA"}

        st = self.session.execute(text("SELECT status FROM matches WHERE match_id='m10'")).scalar_one()
        assert st == "reporting"

        res = self.session.execute(text("SELECT winner_team FROM results WHERE match_id='m10'")).scalar_one()
        assert res == "teamA"

        assert sent == [("matcher.worker.apply_result", ["m10", "teamA"])]
