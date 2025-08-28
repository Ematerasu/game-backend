import asyncio
import httpx
import uuid
import random
import time

API_URL = "http://localhost:8080"
API_KEY = "dev"
N_PLAYERS = 500
GAMES_PER_PLAYER = 10
CONCURRENCY = 100
RECHECK_ENQUEUE_EVERY_SEC = 10
REGIONS = ["EUW", "EUNE", "NA", "CHN", "JPN", "KR", "OCE", "BR", "LAS", "LAN"]

async def register_player(client, username, region):
    idem_key = str(uuid.uuid4())
    r = await client.post(
        f"{API_URL}/players/register",
        headers={"X-Idempotency-Key": idem_key},
        json={"username": username, "region": region},
    )
    r.raise_for_status()
    d = r.json()
    return d["player_id"], d["access_token"]

async def enqueue_player(client, player_id, token):
    r = await client.post(
        f"{API_URL}/matchmaking/queue",
        headers={"x-api-key": API_KEY, "Authorization": f"Bearer {token}"},
        json={"player_id": player_id},
    )
    if r.status_code not in (200, 409):
        r.raise_for_status()

async def report_result(client, match_id, winner):
    r = await client.post(
        f"{API_URL}/matchmaking/match/{match_id}/result",
        headers={"x-api-key": API_KEY},
        json={"winner_team": winner},
    )
    if r.status_code not in (200, 409):
        r.raise_for_status()

async def main():
    limits = httpx.Limits(max_connections=CONCURRENCY, max_keepalive_connections=CONCURRENCY)
    timeout = httpx.Timeout(5.0)
    player_tokens = {}
    games_played = {}
    seen_matches = set()
    last_enqueue_sweep = 0.0

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        regs = [random.choice(REGIONS) for _ in range(N_PLAYERS)]
        regs_counts = {r: 0 for r in REGIONS}
        tasks = []
        for i in range(N_PLAYERS):
            region = regs[i]
            regs_counts[region] += 1
            username = f"user{i}_{region}"
            tasks.append(register_player(client, username, region))
        players = []
        for i in range(0, len(tasks), CONCURRENCY):
            chunk = tasks[i:i+CONCURRENCY]
            res = await asyncio.gather(*chunk, return_exceptions=True)
            for r in res:
                if not isinstance(r, Exception):
                    players.append(r)
        for pid, tok in players:
            player_tokens[pid] = tok
            games_played[pid] = 0
        print(f"registered={len(players)} per_region={{{', '.join(f'{k}:{v}' for k,v in regs_counts.items() if v)}}}")

        init_tasks = [enqueue_player(client, pid, player_tokens[pid]) for pid, _ in players]
        for i in range(0, len(init_tasks), CONCURRENCY):
            chunk = init_tasks[i:i+CONCURRENCY]
            await asyncio.gather(*chunk, return_exceptions=True)
            await asyncio.sleep(0.05)

        total_needed = N_PLAYERS * GAMES_PER_PLAYER
        total_completed = 0
        last_print = time.time()

        async def handle_match(m):
            nonlocal total_completed
            mid = m["match_id"]
            if mid in seen_matches:
                return
            seen_matches.add(mid)
            winner = random.choice(["teamA", "teamB"])
            await report_result(client, mid, winner)
            pd = m.get("players", {})
            pids = [p["player_id"] for p in pd.get("teamA", [])] + [p["player_id"] for p in pd.get("teamB", [])]
            reenq = []
            for pid in pids:
                if pid in games_played and games_played[pid] < GAMES_PER_PLAYER:
                    games_played[pid] += 1
                    total_completed += 1
                    if games_played[pid] < GAMES_PER_PLAYER:
                        reenq.append(pid)
            if reenq:
                tasks3 = [enqueue_player(client, pid, player_tokens[pid]) for pid in reenq]
                for i in range(0, len(tasks3), CONCURRENCY):
                    chunk = tasks3[i:i+CONCURRENCY]
                    await asyncio.gather(*chunk, return_exceptions=True)

        while total_completed < total_needed:
            r = await client.get(f"{API_URL}/matchmaking/matches/latest?limit=50")
            if r.status_code == 200:
                matches = r.json()
                if matches:
                    await asyncio.gather(*(handle_match(m) for m in matches))
            now = time.time()
            if now - last_enqueue_sweep >= RECHECK_ENQUEUE_EVERY_SEC:
                todo = [pid for pid, n in games_played.items() if n < GAMES_PER_PLAYER]
                if todo:
                    tasks4 = [enqueue_player(client, pid, player_tokens[pid]) for pid in todo]
                    for i in range(0, len(tasks4), CONCURRENCY):
                        chunk = tasks4[i:i+CONCURRENCY]
                        await asyncio.gather(*chunk, return_exceptions=True)
                last_enqueue_sweep = now
            if now - last_print > 1.0:
                done_players = sum(1 for v in games_played.values() if v >= GAMES_PER_PLAYER)
                print(f"progress games={total_completed}/{total_needed} players_done={done_players}/{N_PLAYERS} matches_seen={len(seen_matches)}")
                last_print = now
            await asyncio.sleep(0.3)
        print("tournament finished")

if __name__ == "__main__":
    asyncio.run(main())
