import pytest
import uuid

@pytest.mark.e2e
def test_full_match_flow(client, api_key):
    idem = str(uuid.uuid4())

    # 1. register player
    r = client.post(
        "/players/register",
        headers={"X-Idempotency-Key": idem},
        json={"username": "Akame", "region": "EUW"},
    )
    assert r.status_code == 200
    pid = r.json()["player_id"]

    # 2. enqueue
    r = client.post(
        "/matchmaking/queue",
        headers={"X-API-Key": api_key},
        json={"player_id": pid},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "enqueued"

    # 3. status
    r = client.get(f"/matchmaking/queue/{pid}")
    assert r.status_code == 200
    assert r.json()["enqueued"] is True

    # 4. dequeue
    r = client.delete(f"/matchmaking/queue/{pid}", headers={"X-API-Key": api_key})
    assert r.status_code == 200
    assert r.json()["player_id"] == pid

    r = client.get("/matchmaking/match/unknown-id")
    assert r.status_code == 404
