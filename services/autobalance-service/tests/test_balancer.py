from __future__ import annotations

import unittest

from app.balancer import BalanceError, build_balance_preview


def player(index: int, team: int, rating: float, matches: int = 100) -> dict:
    return {
        "fabid": f"player-{index}",
        "name": f"Player {index}",
        "currentTeam": team,
        "displayRating": rating,
        "matches": matches,
    }


class BalancerTests(unittest.TestCase):
    def test_stacked_five_player_teams_are_improved_with_move_limit(self) -> None:
        roster = [player(index, 0, 1400) for index in range(5)]
        roster += [player(index + 5, 1, 900) for index in range(5)]

        preview = build_balance_preview(roster, max_moves=4)

        self.assertTrue(preview["dryRun"])
        self.assertTrue(preview["shouldApply"])
        self.assertLessEqual(len(preview["moves"]), 4)
        self.assertLess(
            preview["proposed"]["probabilitySpread"],
            preview["current"]["probabilitySpread"],
        )
        self.assertEqual(
            [team["size"] for team in preview["proposed"]["teams"]],
            [5, 5],
        )

    def test_fair_teams_do_not_move_players(self) -> None:
        roster = [
            player(0, 0, 1200),
            player(1, 0, 1000),
            player(2, 1, 1200),
            player(3, 1, 1000),
        ]

        preview = build_balance_preview(roster)

        self.assertEqual(preview["algorithm"], "no-change")
        self.assertFalse(preview["shouldApply"])
        self.assertEqual(preview["moves"], [])

    def test_new_player_rating_is_shrunk_toward_default(self) -> None:
        roster = [
            player(0, 0, 1600, matches=0),
            player(1, 0, 1000),
            player(2, 1, 1000),
            player(3, 1, 1000),
        ]

        preview = build_balance_preview(roster)

        self.assertFalse(preview["shouldApply"])
        new_player = preview["current"]["teams"][0]["players"][0]
        self.assertEqual(new_player["effectiveRating"], 1000.0)

    def test_preview_requires_players_on_both_sides(self) -> None:
        with self.assertRaises(BalanceError):
            build_balance_preview([player(0, 0, 1000)])
