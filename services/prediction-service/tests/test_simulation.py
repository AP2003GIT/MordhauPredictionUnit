from __future__ import annotations

import random
import unittest

from app.simulation import build_random_match_prediction


class SimulationTests(unittest.TestCase):
    def test_random_match_prediction_builds_two_five_player_teams(self) -> None:
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

        self.assertEqual(prediction["status"], "ok")
        self.assertEqual(prediction["signals"]["teamSizes"], {"0": 5, "1": 5})
        self.assertEqual(len(prediction["teams"][0]["players"]), 5)
        self.assertEqual(len(prediction["teams"][1]["players"]), 5)
        self.assertAlmostEqual(
            prediction["teams"][0]["probability"] + prediction["teams"][1]["probability"],
            1.0,
        )

    def test_random_match_prediction_requires_enough_players(self) -> None:
        players = [{"fabid": "only-one", "displayRating": 1000}]

        with self.assertRaises(ValueError):
            build_random_match_prediction(players, rng=random.Random(1))
