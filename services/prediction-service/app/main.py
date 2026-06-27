from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .data_client import DataServiceClient, DataServiceError
from .predictor import predict_current_match
from .ratings import build_player_ratings


app = FastAPI(title="Mordhau Prediction Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "prediction-service"}


@app.post("/ingest/history")
def ingest_history(limit: int = Query(default=9999, ge=1, le=20000)) -> dict:
    client = DataServiceClient()
    try:
        return client.post_json("/ingest/history", {"limit": limit})
    except DataServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/predict/current")
def predict_current(history_limit: int = Query(default=9999, ge=1, le=20000)) -> dict:
    client = DataServiceClient()
    try:
        scoreboard = client.get_json("/scoreboard/current", {"save_snapshot": "true"})
        history = client.get_json("/matches/history", {"limit": history_limit, "order": "asc"})
    except DataServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    matches = history.get("matches", [])
    ratings = build_player_ratings(matches if isinstance(matches, list) else [])
    prediction = predict_current_match(scoreboard, ratings).as_dict()
    prediction["historyMatches"] = len(matches) if isinstance(matches, list) else 0
    return prediction


@app.get("/ratings")
def ratings(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    client = DataServiceClient()
    try:
        history = client.get_json("/matches/history", {"limit": 20000, "order": "asc"})
    except DataServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    matches = history.get("matches", [])
    player_ratings = build_player_ratings(matches if isinstance(matches, list) else [])
    sorted_ratings = sorted(
        player_ratings.values(),
        key=lambda player: (player.display_rating, player.matches),
        reverse=True,
    )
    return {"players": [player.as_dict() for player in sorted_ratings[:limit]]}


@app.get("/matches/recent")
def recent_matches(limit: int = Query(default=20, ge=1, le=500)) -> dict:
    client = DataServiceClient()
    try:
        return client.get_json("/matches/recent", {"limit": limit})
    except DataServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

