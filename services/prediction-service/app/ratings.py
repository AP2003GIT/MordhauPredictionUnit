from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


DEFAULT_RATING = 1000.0
K_FACTOR = 32.0


@dataclass
class PlayerRating:
    fabid: str
    name: str = "Unknown"
    rating: float = DEFAULT_RATING
    matches: int = 0
    wins: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    damage: int = 0
    adr_total: int = 0
    teams_seen: set[int] = field(default_factory=set)

    @property
    def win_rate(self) -> float:
        return self.wins / self.matches if self.matches else 0.0

    @property
    def kd(self) -> float:
        return self.kills / max(1, self.deaths)

    @property
    def kda(self) -> float:
        return (self.kills + 0.35 * self.assists) / max(1, self.deaths)

    @property
    def avg_adr(self) -> float:
        return self.adr_total / self.matches if self.matches else 0.0

    @property
    def display_rating(self) -> float:
        experience_bonus = min(60.0, math.log1p(self.matches) * 12.0)
        impact_bonus = min(90.0, max(-60.0, (self.kda - 1.0) * 34.0))
        return self.rating + experience_bonus + impact_bonus

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "fabid": self.fabid,
            "name": self.name,
            "rating": round(self.rating, 1),
            "displayRating": round(self.display_rating, 1),
            "matches": self.matches,
            "wins": self.wins,
            "winRate": round(self.win_rate, 3),
            "kills": self.kills,
            "deaths": self.deaths,
            "assists": self.assists,
            "kd": round(self.kd, 3),
            "kda": round(self.kda, 3),
            "avgAdr": round(self.avg_adr, 1),
        }


def build_player_ratings(matches: list[dict[str, Any]]) -> dict[str, PlayerRating]:
    ratings: dict[str, PlayerRating] = {}

    for match in sorted(matches, key=match_sort_key):
        winner_team = determine_winner(match)
        participants = match.get("players", [])
        if winner_team not in (0, 1) or not isinstance(participants, list):
            continue

        teams = {
            0: [player for player in participants if player.get("team") == 0],
            1: [player for player in participants if player.get("team") == 1],
        }
        if not teams[0] or not teams[1]:
            continue

        for player_data in participants:
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
            team: average_rating(rows, ratings)
            for team, rows in teams.items()
        }

        expected_team_0 = expected_score(team_ratings[0], team_ratings[1])
        expected_by_team = {0: expected_team_0, 1: 1.0 - expected_team_0}

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

    return ratings


def average_rating(players: list[dict[str, Any]], ratings: dict[str, PlayerRating]) -> float:
    values = []
    for player in players:
        fabid = str(player.get("fabid") or "").strip()
        values.append(ratings.get(fabid, PlayerRating(fabid=fabid)).rating)
    return sum(values) / len(values) if values else DEFAULT_RATING


def determine_winner(match: dict[str, Any]) -> int | None:
    iron_score = to_optional_int(match.get("iron_company_score"))
    free_score = to_optional_int(match.get("free_guard_score"))

    if iron_score is None or free_score is None or iron_score == free_score:
        return None

    return 0 if iron_score > free_score else 1


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def match_sort_key(match: dict[str, Any]) -> tuple[str, str]:
    return (str(match.get("date") or ""), str(match.get("match_key") or ""))


def to_int(value: Any) -> int:
    return to_optional_int(value) or 0


def to_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

