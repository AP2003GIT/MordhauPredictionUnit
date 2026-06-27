from __future__ import annotations

import math
import random
from typing import Any

from .config import TEAM_NAMES
from .ratings import DEFAULT_RATING


def build_random_match_prediction(
    players: list[dict[str, Any]],
    *,
    team_size: int = 5,
    rng: random.Random | random.SystemRandom | None = None,
) -> dict[str, Any]:
    required_players = team_size * 2
    if team_size < 1:
        raise ValueError("Team size must be at least 1.")

    pool = [normalize_player(player) for player in players]
    pool = [player for player in pool if player["fabid"] and player["rating"] > 0]

    if len(pool) < required_players:
        raise ValueError(f"Need at least {required_players} rated players for a random match.")

    chooser = rng or random.SystemRandom()
    selected = chooser.sample(pool, required_players)
    team_zero_players = selected[:team_size]
    team_one_players = selected[team_size:]

    team_zero = summarize_generated_team(0, team_zero_players)
    team_one = summarize_generated_team(1, team_one_players)

    rating_diff = team_zero["averageRating"] - team_one["averageRating"]
    team_zero_probability = sigmoid(rating_diff / 180.0)
    team_zero["probability"] = round(team_zero_probability, 4)
    team_one["probability"] = round(1.0 - team_zero_probability, 4)

    sample_size = min(
        sum(player["historicalMatches"] for player in team_zero_players),
        sum(player["historicalMatches"] for player in team_one_players),
    )
    confidence = min(0.95, 0.25 + math.log1p(sample_size) / 9.0)

    return {
        "status": "ok",
        "mode": f"random-{team_size}v{team_size}",
        "message": "Random 5v5 prediction generated from stored player ratings.",
        "confidence": round(confidence, 3),
        "teams": [team_zero, team_one],
        "signals": {
            "ratingDiff": round(rating_diff, 2),
            "liveImpactDiff": 0.0,
            "scoreDiff": 0,
            "teamSizes": {"0": team_size, "1": team_size},
            "sampledPlayers": required_players,
            "predictionInput": "rating-only",
        },
    }


def normalize_player(player: dict[str, Any]) -> dict[str, Any]:
    rating = to_float(player.get("displayRating"), DEFAULT_RATING)
    matches = to_int(player.get("matches") or player.get("aggregateMatches"))

    return {
        "fabid": str(player.get("fabid") or "").strip(),
        "name": str(player.get("name") or "Unknown"),
        "rating": round(rating, 1),
        "historicalMatches": matches,
        "kills": to_int(player.get("kills") or player.get("aggregateKills")),
        "deaths": to_int(player.get("deaths") or player.get("aggregateDeaths")),
        "assists": to_int(player.get("assists") or player.get("aggregateAssists")),
        "damage": 0,
        "adr": round(to_float(player.get("avgAdr")), 1),
        "liveImpact": 0.0,
        "winRate": round(to_float(player.get("winRate")), 3),
        "kd": round(to_float(player.get("kd")), 3),
        "kda": round(to_float(player.get("kda")), 3),
        "ratingSource": player.get("ratingSource") or "unknown",
        "steamAvatar": player.get("steamAvatar"),
    }


def summarize_generated_team(team: int, players: list[dict[str, Any]]) -> dict[str, Any]:
    average_rating = sum(player["rating"] for player in players) / len(players)
    return {
        "team": team,
        "name": TEAM_NAMES[team],
        "probability": 0.0,
        "averageRating": round(average_rating, 1),
        "liveImpact": 0.0,
        "currentScore": None,
        "players": sorted(players, key=lambda player: player["rating"], reverse=True),
    }


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
