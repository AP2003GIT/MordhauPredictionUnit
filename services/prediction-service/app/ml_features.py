from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .ratings import (
    DEFAULT_RATING,
    K_FACTOR,
    PlayerRating,
    determine_winner,
    expected_score,
    match_sort_key,
    to_int,
)


FEATURE_NAMES = [
    "avg_rating_diff",
    "top_rating_diff",
    "weakest_rating_diff",
    "rating_spread_diff",
    "avg_matches_diff",
    "total_matches_diff",
    "avg_win_rate_diff",
    "avg_kd_diff",
    "avg_kda_diff",
    "avg_adr_diff",
    "team_size_diff",
]


@dataclass(frozen=True)
class TrainingExample:
    match_key: str
    match_date: str
    label: int
    features: dict[str, float]


@dataclass(frozen=True)
class TrainingDataset:
    examples: list[TrainingExample]
    skipped_matches: int
    final_ratings: dict[str, PlayerRating]


def build_training_dataset(matches: list[dict[str, Any]]) -> TrainingDataset:
    ratings: dict[str, PlayerRating] = {}
    examples: list[TrainingExample] = []
    skipped_matches = 0

    for match in sorted(matches, key=match_sort_key):
        winner_team = determine_winner(match)
        teams = split_match_teams(match)

        if winner_team not in (0, 1) or not teams:
            skipped_matches += 1
            continue

        features = build_team_feature_differences(teams, ratings)
        examples.append(
            TrainingExample(
                match_key=str(match.get("match_key") or ""),
                match_date=str(match.get("date") or ""),
                label=1 if winner_team == 0 else 0,
                features=features,
            )
        )
        update_ratings_after_match(match, teams, ratings, winner_team)

    return TrainingDataset(
        examples=examples,
        skipped_matches=skipped_matches,
        final_ratings=ratings,
    )


def split_match_teams(match: dict[str, Any]) -> dict[int, list[dict[str, Any]]] | None:
    participants = match.get("players", [])
    if not isinstance(participants, list):
        return None

    teams = {
        0: [player for player in participants if player.get("team") == 0],
        1: [player for player in participants if player.get("team") == 1],
    }
    if not teams[0] or not teams[1]:
        return None
    return teams


def split_scoreboard_teams(players: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]] | None:
    teams = {0: [], 1: []}
    for player in players:
        if not isinstance(player, dict):
            continue
        team = player.get("team")
        if team is None:
            team = player.get("Team")
        try:
            team = int(team)
        except (TypeError, ValueError):
            continue
        if team in teams:
            teams[team].append(player)

    if not teams[0] or not teams[1]:
        return None
    return teams


def prediction_teams_to_feature_teams(prediction: dict[str, Any]) -> dict[int, list[dict[str, Any]]] | None:
    teams = {0: [], 1: []}
    for team in prediction.get("teams", []):
        if not isinstance(team, dict):
            continue
        team_id = team.get("team")
        if team_id in teams and isinstance(team.get("players"), list):
            teams[team_id] = team["players"]

    if not teams[0] or not teams[1]:
        return None
    return teams


def build_team_feature_differences(
    teams: dict[int, list[dict[str, Any]]],
    ratings: dict[str, PlayerRating] | None = None,
) -> dict[str, float]:
    team_zero = summarize_team_features(teams[0], ratings or {})
    team_one = summarize_team_features(teams[1], ratings or {})

    return {
        "avg_rating_diff": team_zero["avg_rating"] - team_one["avg_rating"],
        "top_rating_diff": team_zero["top_rating"] - team_one["top_rating"],
        "weakest_rating_diff": team_zero["weakest_rating"] - team_one["weakest_rating"],
        "rating_spread_diff": team_zero["rating_spread"] - team_one["rating_spread"],
        "avg_matches_diff": team_zero["avg_matches"] - team_one["avg_matches"],
        "total_matches_diff": team_zero["total_matches"] - team_one["total_matches"],
        "avg_win_rate_diff": team_zero["avg_win_rate"] - team_one["avg_win_rate"],
        "avg_kd_diff": team_zero["avg_kd"] - team_one["avg_kd"],
        "avg_kda_diff": team_zero["avg_kda"] - team_one["avg_kda"],
        "avg_adr_diff": team_zero["avg_adr"] - team_one["avg_adr"],
        "team_size_diff": team_zero["team_size"] - team_one["team_size"],
    }


def summarize_team_features(
    players: list[dict[str, Any]],
    ratings: dict[str, PlayerRating],
) -> dict[str, float]:
    snapshots = [player_snapshot(player, ratings) for player in players]
    rating_values = [snapshot["rating"] for snapshot in snapshots]

    return {
        "team_size": float(len(snapshots)),
        "avg_rating": average(rating_values, DEFAULT_RATING),
        "top_rating": max(rating_values) if rating_values else DEFAULT_RATING,
        "weakest_rating": min(rating_values) if rating_values else DEFAULT_RATING,
        "rating_spread": (max(rating_values) - min(rating_values)) if rating_values else 0.0,
        "avg_matches": average([snapshot["matches"] for snapshot in snapshots]),
        "total_matches": sum(snapshot["matches"] for snapshot in snapshots),
        "avg_win_rate": average([snapshot["win_rate"] for snapshot in snapshots]),
        "avg_kd": average([snapshot["kd"] for snapshot in snapshots]),
        "avg_kda": average([snapshot["kda"] for snapshot in snapshots]),
        "avg_adr": average([snapshot["avg_adr"] for snapshot in snapshots]),
    }


def player_snapshot(
    player: dict[str, Any],
    ratings: dict[str, PlayerRating],
) -> dict[str, float]:
    fabid = str(player.get("fabid") or player.get("FabID") or "").strip()
    rating = ratings.get(fabid)
    if rating:
        return {
            "rating": rating.display_rating,
            "matches": float(rating.matches),
            "win_rate": rating.win_rate,
            "kd": rating.kd,
            "kda": rating.kda,
            "avg_adr": rating.avg_adr,
        }

    return {
        "rating": float_from_keys(player, ["displayRating", "rating"], DEFAULT_RATING),
        "matches": float_from_keys(player, ["historicalMatches", "matches", "aggregateMatches"], 0.0),
        "win_rate": float_from_keys(player, ["winRate"], 0.0),
        "kd": float_from_keys(player, ["kd"], 0.0),
        "kda": float_from_keys(player, ["kda"], 0.0),
        "avg_adr": float_from_keys(player, ["avgAdr", "adr", "ADR"], 0.0),
    }


def update_ratings_after_match(
    match: dict[str, Any],
    teams: dict[int, list[dict[str, Any]]],
    ratings: dict[str, PlayerRating],
    winner_team: int,
) -> None:
    for player_data in match.get("players", []):
        if not isinstance(player_data, dict):
            continue
        fabid = str(player_data.get("fabid") or "").strip()
        if not fabid:
            continue
        player = ratings.setdefault(fabid, PlayerRating(fabid=fabid))
        player.name = (
            player_data.get("steamUsername")
            or player_data.get("playername")
            or player.name
        )

    team_ratings = {
        team: average_raw_rating(rows, ratings)
        for team, rows in teams.items()
    }
    expected_team_zero = expected_score(team_ratings[0], team_ratings[1])
    expected_by_team = {0: expected_team_zero, 1: 1.0 - expected_team_zero}

    for team, rows in teams.items():
        actual = 1.0 if team == winner_team else 0.0
        team_size_factor = 1.0 / math.sqrt(len(rows))

        for player_data in rows:
            fabid = str(player_data.get("fabid") or "").strip()
            if not fabid:
                continue

            player = ratings[fabid]
            player.rating += K_FACTOR * team_size_factor * (actual - expected_by_team[team])
            player.matches += 1
            player.wins += 1 if actual == 1.0 else 0
            player.kills += to_int(player_data.get("kills"))
            player.deaths += to_int(player_data.get("deaths"))
            player.assists += to_int(player_data.get("assists"))
            player.damage += to_int(player_data.get("dmg"))
            player.adr_total += to_int(player_data.get("adr"))
            player.teams_seen.add(team)


def average_raw_rating(
    players: list[dict[str, Any]],
    ratings: dict[str, PlayerRating],
) -> float:
    values = []
    for player in players:
        fabid = str(player.get("fabid") or "").strip()
        values.append(ratings.get(fabid, PlayerRating(fabid=fabid)).rating)
    return average(values, DEFAULT_RATING)


def average(values: list[float], default: float = 0.0) -> float:
    return sum(values) / len(values) if values else default


def float_from_keys(payload: dict[str, Any], keys: list[str], default: float = 0.0) -> float:
    for key in keys:
        value = payload.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default
