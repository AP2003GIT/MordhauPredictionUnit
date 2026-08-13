from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import math
import random
from typing import Any

from .activity import active_skm_player_counts, skm_matches
from .config import ACTIVE_SKM_MIN_MATCHES, ACTIVE_SKM_WINDOW_DAYS, MODEL_PATH
from .data_client import DataServiceClient, DataServiceError
from .ml_features import (
    build_team_feature_differences,
    build_training_dataset,
    prediction_teams_to_feature_teams,
    split_scoreboard_teams,
)
from .ml_model import load_model, save_model, train_logistic_model
from .predictor import predict_current_match
from .ratings import build_player_ratings
from .simulation import build_random_match_prediction


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
    attach_ml_prediction_from_scoreboard(prediction, scoreboard, ratings)
    prediction["historyMatches"] = len(matches) if isinstance(matches, list) else 0
    return prediction


@app.get("/ratings")
def ratings(limit: int = Query(default=20000, ge=1, le=20000)) -> dict:
    players = load_player_catalog()
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
        "activityRule": {
            "gamemode": "Skirmish",
            "windowDays": ACTIVE_SKM_WINDOW_DAYS,
            "minimumMatches": ACTIVE_SKM_MIN_MATCHES,
        },
    }


@app.get("/predict/random")
def predict_random(
    team_size: int = Query(default=5, ge=1, le=16),
    seed: int | None = Query(default=None),
) -> dict:
    players = load_player_catalog()
    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    try:
        prediction = build_random_match_prediction(players, team_size=team_size, rng=rng)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    attach_ml_prediction_from_prediction(prediction)
    return prediction


@app.post("/model/train")
def train_model(history_limit: int = Query(default=20000, ge=10, le=20000)) -> dict:
    matches = load_history_matches(history_limit)
    dataset = build_training_dataset(matches)
    try:
        model = train_logistic_model(dataset.examples)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    save_model(model, MODEL_PATH)
    return {
        "status": "trained",
        "historyMatches": len(matches),
        "trainingRows": len(dataset.examples),
        "skippedMatches": dataset.skipped_matches,
        "modelPath": str(MODEL_PATH),
        **model.summary(),
    }


@app.get("/model/status")
def model_status() -> dict:
    model = load_model(MODEL_PATH)
    if not model:
        return {
            "available": False,
            "modelPath": str(MODEL_PATH),
            "message": "No trained model has been saved yet.",
        }
    return {**model.summary(), "modelPath": str(MODEL_PATH)}


@app.get("/matches/recent")
def recent_matches(limit: int = Query(default=20, ge=1, le=500)) -> dict:
    client = DataServiceClient()
    try:
        return client.get_json("/matches/recent", {"limit": limit})
    except DataServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def load_player_catalog() -> list[dict]:
    matches = load_history_matches(20000)
    skirmish_history = skm_matches(matches)
    client = DataServiceClient()
    try:
        known_players = client.get_json("/players/all", {"limit": 20000})
    except DataServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    player_ratings = build_player_ratings(skirmish_history)
    active_counts = active_skm_player_counts(
        skirmish_history,
        window_days=ACTIVE_SKM_WINDOW_DAYS,
        min_matches=ACTIVE_SKM_MIN_MATCHES,
    )
    players = merge_player_ratings(
        player_ratings,
        known_players.get("players", []) if isinstance(known_players, dict) else [],
    )
    active_players = []
    for player in players:
        fabid = str(player.get("fabid") or "").strip()
        if fabid not in active_counts:
            continue
        active_players.append({**player, "activeSkmMatches": active_counts[fabid]})
    return active_players


def load_history_matches(limit: int) -> list[dict]:
    client = DataServiceClient()
    try:
        history = client.get_json("/matches/history", {"limit": limit, "order": "asc"})
    except DataServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    matches = history.get("matches", [])
    return matches if isinstance(matches, list) else []


def attach_ml_prediction_from_scoreboard(
    prediction: dict[str, Any],
    scoreboard: dict[str, Any],
    ratings: dict,
) -> None:
    raw_players = scoreboard.get("scoreboard", [])
    if not isinstance(raw_players, list):
        prediction["mlPrediction"] = {"available": False}
        return

    teams = split_scoreboard_teams(raw_players)
    attach_ml_prediction(prediction, teams, ratings)


def attach_ml_prediction_from_prediction(prediction: dict[str, Any]) -> None:
    teams = prediction_teams_to_feature_teams(prediction)
    attach_ml_prediction(prediction, teams, None)


def attach_ml_prediction(
    prediction: dict[str, Any],
    teams: dict[int, list[dict[str, Any]]] | None,
    ratings: dict | None,
) -> None:
    model = load_model(MODEL_PATH)
    if not model:
        prediction["mlPrediction"] = {"available": False}
        return

    if not teams:
        prediction["mlPrediction"] = {
            "available": False,
            "reason": "Need players on both teams before ML can score the match.",
        }
        return

    features = build_team_feature_differences(teams, ratings)
    team_zero_probability = model.predict_probability(features)
    prediction["mlPrediction"] = {
        "available": True,
        "source": "trained-history",
        "modelVersion": model.summary()["version"],
        "team0Probability": round(team_zero_probability, 4),
        "team1Probability": round(1.0 - team_zero_probability, 4),
        "favoredTeam": 0 if team_zero_probability >= 0.5 else 1,
        "topSignals": model.explain(features),
    }


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
