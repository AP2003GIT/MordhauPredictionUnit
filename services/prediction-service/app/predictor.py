from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .config import TEAM_NAMES
from .ratings import DEFAULT_RATING, PlayerRating


@dataclass(frozen=True)
class TeamSummary:
    average_rating: float
    live_impact: float
    players: list[dict[str, Any]]


@dataclass(frozen=True)
class TeamPrediction:
    team: int
    name: str
    probability: float
    average_rating: float
    live_impact: float
    current_score: int | None
    players: list[dict[str, Any]]


@dataclass(frozen=True)
class Prediction:
    status: str
    message: str
    teams: list[TeamPrediction]
    confidence: float
    signals: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "confidence": round(self.confidence, 3),
            "signals": self.signals,
            "teams": [
                {
                    "team": team.team,
                    "name": team.name,
                    "probability": round(team.probability, 4),
                    "averageRating": round(team.average_rating, 1),
                    "liveImpact": round(team.live_impact, 1),
                    "currentScore": team.current_score,
                    "players": team.players,
                }
                for team in self.teams
            ],
        }


def predict_current_match(
    scoreboard_payload: dict[str, Any],
    ratings: dict[str, PlayerRating],
) -> Prediction:
    scoreboard = scoreboard_payload.get("scoreboard", [])
    if not isinstance(scoreboard, list) or not scoreboard:
        return Prediction(
            status="idle",
            message="No live players are currently present in the scoreboard.",
            teams=[],
            confidence=0.0,
            signals={"scoreboardAgeSeconds": scoreboard_payload.get("ageSeconds")},
        )

    teams = {0: [], 1: []}
    for raw_player in scoreboard:
        if not isinstance(raw_player, dict):
            continue
        team = int_from_keys(raw_player, ["team", "Team"])
        if team in teams:
            teams[team].append(raw_player)

    if not teams[0] or not teams[1]:
        return Prediction(
            status="waiting",
            message="Need players on both teams before a prediction is meaningful.",
            teams=[],
            confidence=0.0,
            signals={"teamSizes": {str(team): len(players) for team, players in teams.items()}},
        )

    current_scores = extract_scores(scoreboard_payload)
    team_summaries = {
        team: summarize_team(team, players, ratings, current_scores.get(team))
        for team, players in teams.items()
    }

    rating_diff = team_summaries[0].average_rating - team_summaries[1].average_rating
    live_diff = team_summaries[0].live_impact - team_summaries[1].live_impact
    score_diff = (current_scores.get(0) or 0) - (current_scores.get(1) or 0)

    logit = (rating_diff / 180.0) + (live_diff / 120.0) + (score_diff * 0.65)
    team_0_probability = sigmoid(logit)

    predicted_teams = [
        TeamPrediction(
            team=0,
            name=TEAM_NAMES[0],
            probability=team_0_probability,
            average_rating=team_summaries[0].average_rating,
            live_impact=team_summaries[0].live_impact,
            current_score=current_scores.get(0),
            players=team_summaries[0].players,
        ),
        TeamPrediction(
            team=1,
            name=TEAM_NAMES[1],
            probability=1.0 - team_0_probability,
            average_rating=team_summaries[1].average_rating,
            live_impact=team_summaries[1].live_impact,
            current_score=current_scores.get(1),
            players=team_summaries[1].players,
        ),
    ]

    sample_size = min(
        sum(player.get("historicalMatches", 0) for player in team_summaries[0].players),
        sum(player.get("historicalMatches", 0) for player in team_summaries[1].players),
    )
    confidence = min(0.95, 0.25 + math.log1p(sample_size) / 9.0)

    return Prediction(
        status="ok",
        message="Prediction generated from player ratings and live scoreboard state.",
        teams=predicted_teams,
        confidence=confidence,
        signals={
            "ratingDiff": round(rating_diff, 2),
            "liveImpactDiff": round(live_diff, 2),
            "scoreDiff": score_diff,
            "teamSizes": {str(team): len(players) for team, players in teams.items()},
            "scoreboardAgeSeconds": scoreboard_payload.get("ageSeconds"),
            "isStale": scoreboard_payload.get("isStale"),
        },
    )


def summarize_team(
    team: int,
    players: list[dict[str, Any]],
    ratings: dict[str, PlayerRating],
    current_score: int | None,
) -> TeamSummary:
    summarized_players: list[dict[str, Any]] = []
    total_rating = 0.0
    total_live_impact = 0.0

    for raw_player in players:
        fabid = str(raw_player.get("fabid") or raw_player.get("FabID") or "").strip()
        rating = ratings.get(fabid)
        display_rating = rating.display_rating if rating else DEFAULT_RATING
        live_impact = live_player_impact(raw_player)

        total_rating += display_rating
        total_live_impact += live_impact
        summarized_players.append(
            {
                "fabid": fabid,
                "name": player_name(raw_player, rating),
                "rating": round(display_rating, 1),
                "historicalMatches": rating.matches if rating else 0,
                "kills": int_from_keys(raw_player, ["kills", "Kills"], default=0),
                "deaths": int_from_keys(raw_player, ["deaths", "Deaths"], default=0),
                "assists": int_from_keys(raw_player, ["assists", "Assists"], default=0),
                "damage": int_from_keys(raw_player, ["dmg", "damage", "Damage"], default=0),
                "adr": int_from_keys(raw_player, ["adr", "ADR"], default=0),
                "liveImpact": round(live_impact, 1),
            }
        )

    return TeamSummary(
        average_rating=total_rating / len(players),
        live_impact=total_live_impact / len(players) + (current_score or 0) * 12.0,
        players=sorted(summarized_players, key=lambda player: player["rating"], reverse=True),
    )


def live_player_impact(player: dict[str, Any]) -> float:
    kills = int_from_keys(player, ["kills", "Kills"], default=0)
    deaths = int_from_keys(player, ["deaths", "Deaths"], default=0)
    assists = int_from_keys(player, ["assists", "Assists"], default=0)
    damage = int_from_keys(player, ["dmg", "damage", "Damage"], default=0)
    adr = int_from_keys(player, ["adr", "ADR"], default=0)

    return kills * 16.0 + assists * 5.0 + damage * 0.035 + adr * 0.3 - deaths * 11.0


def extract_scores(payload: dict[str, Any]) -> dict[int, int | None]:
    return {
        0: int_from_keys(
            payload,
            ["iron_company_score", "ironCompanyScore", "iron_score", "team0Score"],
        ),
        1: int_from_keys(
            payload,
            ["free_guard_score", "freeGuardScore", "free_score", "team1Score"],
        ),
    }


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def player_name(raw_player: dict[str, Any], rating: PlayerRating | None) -> str:
    for key in ("steamUsername", "playername", "name", "Name"):
        value = raw_player.get(key)
        if value:
            return str(value)
    return rating.name if rating else "Unknown"


def int_from_keys(
    payload: dict[str, Any],
    keys: list[str],
    default: int | None = None,
) -> int | None:
    for key in keys:
        value = payload.get(key)
        if value is None or value == "":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return default

