from __future__ import annotations

import random

from app.simulation import build_random_match_prediction


def test_random_match_prediction_builds_two_five_player_teams() -> None:
    players = [
        {
            "fabid": f"player-{index}",
            "name": f"Player {index}",
            "displayRating": 1000 + index * 12,
            "matches": 25 + index,
            "wins": 10,
            "kills": 100 + index,
            "deaths": 60,
            "assists": 30,
            "kd": 1.5,
            "kda": 1.7,
            "avgAdr": 70,
            "ratingSource": "match-history",
        }
        for index in range(12)
    ]

    prediction = build_random_match_prediction(players, rng=random.Random(7))

    assert prediction["status"] == "ok"
    assert prediction["signals"]["teamSizes"] == {"0": 5, "1": 5}
    assert len(prediction["teams"][0]["players"]) == 5
    assert len(prediction["teams"][1]["players"]) == 5
    assert abs(prediction["teams"][0]["probability"] + prediction["teams"][1]["probability"] - 1.0) < 0.0001


def test_random_match_prediction_requires_enough_players() -> None:
    players = [{"fabid": "only-one", "displayRating": 1000}]

    try:
        build_random_match_prediction(players, rng=random.Random(1))
    except ValueError:
        return

    raise AssertionError("Expected a ValueError when fewer than 10 players are available.")
