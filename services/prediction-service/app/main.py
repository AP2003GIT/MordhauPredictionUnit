from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import math

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
def ratings(limit: int = Query(default=20000, ge=1, le=20000)) -> dict:
    client = DataServiceClient()
    try:
        history = client.get_json("/matches/history", {"limit": 20000, "order": "asc"})
        known_players = client.get_json("/players/all", {"limit": 20000})
    except DataServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    matches = history.get("matches", [])
    player_ratings = build_player_ratings(matches if isinstance(matches, list) else [])
    players = merge_player_ratings(
        player_ratings,
        known_players.get("players", []) if isinstance(known_players, dict) else [],
    )
    sorted_players = sorted(
        players,
        key=lambda player: (player["displayRating"], player["matches"]),
        reverse=True,
    )
    returned_players = sorted_players[:limit]
    return {
        "players": returned_players,
        "count": len(sorted_players),
        "returned": len(returned_players),
    }


@app.get("/matches/recent")
def recent_matches(limit: int = Query(default=20, ge=1, le=500)) -> dict:
    client = DataServiceClient()
    try:
        return client.get_json("/matches/recent", {"limit": limit})
    except DataServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def merge_player_ratings(player_ratings: dict, known_players: list) -> list[dict]:
    merged = {fabid: rating.as_dict() for fabid, rating in player_ratings.items()}

    for player in known_players:
        if not isinstance(player, dict):
            continue
        fabid = str(player.get("fabid") or "").strip()
        if not fabid:
            continue

        aggregate = aggregate_player_rating(player)
        if fabid in merged:
            merged[fabid] = {
                **merged[fabid],
                "aggregateMatches": aggregate["matches"],
                "aggregateKills": aggregate["kills"],
                "aggregateDeaths": aggregate["deaths"],
                "aggregateAssists": aggregate["assists"],
                "steamAvatar": player.get("steamAvatar"),
                "ratingSource": "match-history",
            }
        else:
            merged[fabid] = aggregate

    return list(merged.values())


def aggregate_player_rating(player: dict) -> dict:
    matches = to_int(player.get("matchesPlayed"))
    kills = to_int(player.get("totalKills"))
    deaths = to_int(player.get("totalDeaths"))
    assists = to_int(player.get("totalAssists"))
    kd = to_float(player.get("kd"))
    kda = (kills + 0.35 * assists) / max(1, deaths)

    experience_bonus = min(50.0, math.log1p(matches) * 8.0)
    impact_bonus = min(80.0, max(-70.0, (kda - 1.0) * 30.0))
    display_rating = 1000.0 + experience_bonus + impact_bonus

    return {
        "fabid": str(player.get("fabid") or ""),
        "name": player.get("steamUsername") or "Unknown",
        "rating": 1000.0,
        "displayRating": round(display_rating, 1),
        "matches": matches,
        "wins": 0,
        "winRate": 0.0,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "kd": round(kd, 3),
        "kda": round(kda, 3),
        "avgAdr": 0.0,
        "steamAvatar": player.get("steamAvatar"),
        "ratingSource": "aggregate-stats",
    }


def to_int(value) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def to_float(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
