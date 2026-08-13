from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import time
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import AUTOSYNC_INTERVAL_SECONDS, AUTOSYNC_MATCH_LIMIT, AUTOSYNC_PLAYER_LIMIT
from .needys_client import NeedysApiError, NeedysClient
from .storage import (
    connect,
    database_stats,
    init_db,
    load_history_matches,
    load_players,
    save_scoreboard_snapshot,
    upsert_matches,
    upsert_players,
)
from .sync import sync_needys_stats


sync_status: dict[str, Any] = {
    "enabled": AUTOSYNC_INTERVAL_SECONDS > 0,
    "intervalSeconds": AUTOSYNC_INTERVAL_SECONDS,
    "matchLimit": AUTOSYNC_MATCH_LIMIT,
    "playerLimit": AUTOSYNC_PLAYER_LIMIT,
    "running": False,
    "lastAttemptAt": None,
    "lastSuccessAt": None,
    "lastError": None,
    "lastResult": None,
}
sync_lock = Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_incremental_sync() -> dict[str, int]:
    with sync_lock:
        with connect() as connection:
            return sync_needys_stats(
                NeedysClient(),
                connection,
                match_limit=AUTOSYNC_MATCH_LIMIT,
                player_limit=AUTOSYNC_PLAYER_LIMIT,
            )


async def autosync_loop() -> None:
    while True:
        started = time.monotonic()
        sync_status["running"] = True
        sync_status["lastAttemptAt"] = utc_now()
        try:
            result = await asyncio.to_thread(run_incremental_sync)
            sync_status["lastResult"] = result
            sync_status["lastSuccessAt"] = utc_now()
            sync_status["lastError"] = None
        except Exception as exc:  # The worker must stay alive after transient upstream failures.
            sync_status["lastError"] = str(exc) or exc.__class__.__name__
        finally:
            sync_status["running"] = False

        elapsed = time.monotonic() - started
        await asyncio.sleep(max(1.0, AUTOSYNC_INTERVAL_SECONDS - elapsed))


@asynccontextmanager
async def lifespan(_: FastAPI):
    with connect() as connection:
        init_db(connection)

    task = None
    if AUTOSYNC_INTERVAL_SECONDS > 0:
        task = asyncio.create_task(autosync_loop())
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="Mordhau Data Service", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": "data-service",
        "autosyncEnabled": bool(sync_status["enabled"]),
    }


@app.post("/ingest/history")
def ingest_history(limit: int = Query(default=9999, ge=1, le=20000)) -> dict[str, int]:
    client = NeedysClient()
    try:
        matches = client.recent_matches(limit=limit)
        players = client.most_active_players(limit=limit)
    except NeedysApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    with sync_lock:
        with connect() as connection:
            stored = upsert_matches(connection, matches)
            players_stored = upsert_players(connection, players)
            stats = database_stats(connection)

    return {
        "fetched": len(matches),
        "stored": stored,
        "playersFetched": len(players),
        "playersStored": players_stored,
        **stats,
    }


@app.post("/ingest/players")
def ingest_players(limit: int = Query(default=9999, ge=1, le=20000)) -> dict[str, int]:
    client = NeedysClient()
    try:
        players = client.most_active_players(limit=limit)
    except NeedysApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    with sync_lock:
        with connect() as connection:
            stored = upsert_players(connection, players)
            stats = database_stats(connection)

    return {"fetched": len(players), "stored": stored, **stats}


@app.get("/scoreboard/current")
def current_scoreboard(save_snapshot: bool = True) -> dict:
    client = NeedysClient()
    try:
        payload = client.dashboard_scoreboard()
    except NeedysApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if save_snapshot:
        with sync_lock:
            with connect() as connection:
                save_scoreboard_snapshot(connection, payload)

    return payload


@app.get("/matches/history")
def history_matches(
    limit: int = Query(default=9999, ge=1, le=20000),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> dict:
    with connect() as connection:
        matches = load_history_matches(connection, limit=limit, ascending=order == "asc")
    return {"matches": matches, "count": len(matches)}


@app.get("/matches/recent")
def recent_matches(limit: int = Query(default=20, ge=1, le=500)) -> dict:
    with connect() as connection:
        matches = load_history_matches(connection, limit=limit, ascending=False)
    return {"matches": matches, "count": len(matches)}


@app.get("/players/all")
def all_players(limit: int = Query(default=20000, ge=1, le=20000)) -> dict:
    with connect() as connection:
        players = load_players(connection, limit=limit)
    return {"players": players, "count": len(players)}


@app.get("/stats/database")
def stats() -> dict[str, int]:
    with connect() as connection:
        return database_stats(connection)


@app.get("/stats/sync")
def stats_sync() -> dict[str, Any]:
    return dict(sync_status)
