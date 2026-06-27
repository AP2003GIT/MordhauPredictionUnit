from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .needys_client import NeedysApiError, NeedysClient
from .storage import (
    connect,
    database_stats,
    init_db,
    load_history_matches,
    save_scoreboard_snapshot,
    upsert_matches,
)


app = FastAPI(title="Mordhau Data Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    with connect() as connection:
        init_db(connection)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "data-service"}


@app.post("/ingest/history")
def ingest_history(limit: int = Query(default=9999, ge=1, le=20000)) -> dict[str, int]:
    client = NeedysClient()
    try:
        matches = client.recent_matches(limit=limit)
    except NeedysApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    with connect() as connection:
        stored = upsert_matches(connection, matches)
        stats = database_stats(connection)

    return {"fetched": len(matches), "stored": stored, **stats}


@app.get("/scoreboard/current")
def current_scoreboard(save_snapshot: bool = True) -> dict:
    client = NeedysClient()
    try:
        payload = client.dashboard_scoreboard()
    except NeedysApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if save_snapshot:
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


@app.get("/stats/database")
def stats() -> dict[str, int]:
    with connect() as connection:
        return database_stats(connection)

