from __future__ import annotations

import unittest

from app.activity import active_skm_player_counts, skm_matches


def make_match(index: int, fabids: list[str], gamemode: str = "Skirmish") -> dict:
    return {
        "match_key": f"match-{index}",
        "date": f"2026-07-{index:02d} 12:00",
        "gamemode": gamemode,
        "players": [{"fabid": fabid} for fabid in fabids],
    }


class ActivityTests(unittest.TestCase):
    def test_only_repeated_recent_skm_players_are_active(self) -> None:
        matches = [make_match(index, ["regular", "guest"]) for index in range(1, 6)]
        matches.append(make_match(6, ["frontline-only"], gamemode="Frontline"))
        matches.append(
            {
                **make_match(7, ["regular", "regular"]),
                "date": "2026-09-01 12:00",
            }
        )

        counts = active_skm_player_counts(matches, window_days=90, min_matches=5)

        self.assertEqual(counts, {"regular": 6, "guest": 5})
        self.assertEqual(len(skm_matches(matches)), 6)

    def test_old_players_fall_outside_activity_window(self) -> None:
        old_matches = [make_match(index, ["old-regular"]) for index in range(1, 6)]
        latest = {**make_match(20, ["current"]), "date": "2026-09-01 12:00"}

        counts = active_skm_player_counts(
            [*old_matches, latest],
            window_days=30,
            min_matches=1,
        )

        self.assertEqual(counts, {"current": 1})
