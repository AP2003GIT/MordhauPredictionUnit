from __future__ import annotations

import sqlite3
import unittest

from app.storage import (
    database_stats,
    init_db,
    load_active_skm_player_counts,
    load_history_matches,
    load_players,
    prune_players,
    upsert_matches,
    upsert_players,
)
from app.sync import sync_needys_stats


def make_match(
    players: list[dict],
    *,
    match_key: str = "match-1",
    date: str = "2026-07-15 12:00",
    gamemode: str = "Skirmish",
) -> dict:
    return {
        "match_key": match_key,
        "date": date,
        "gamemode": gamemode,
        "iron_company_score": 7,
        "free_guard_score": 4,
        "players": players,
    }


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        init_db(self.connection)

    def tearDown(self) -> None:
        self.connection.close()

    def test_match_round_trip_and_stats(self) -> None:
        match = make_match(
            [
                {"fabid": "iron", "team": 0, "kills": 8},
                {"fabid": "guard", "team": 1, "kills": 4},
            ]
        )

        stored = upsert_matches(self.connection, [match])

        self.assertEqual(stored, 1)
        self.assertEqual(load_history_matches(self.connection), [match])
        self.assertEqual(database_stats(self.connection)["playerMatches"], 2)

    def test_reingestion_replaces_removed_players(self) -> None:
        original = make_match(
            [
                {"fabid": "iron", "team": 0},
                {"fabid": "guard", "team": 1},
            ]
        )
        corrected = make_match([{"fabid": "iron", "team": 0}])

        upsert_matches(self.connection, [original])
        upsert_matches(self.connection, [corrected])

        rows = self.connection.execute(
            "SELECT fabid FROM player_matches WHERE match_key = ? ORDER BY fabid",
            ("match-1",),
        ).fetchall()
        self.assertEqual([row["fabid"] for row in rows], ["iron"])

    def test_incremental_sync_uses_bounded_limits_and_upserts(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.match_limit = 0
                self.player_limit = 0

            def recent_matches(self, limit: int) -> list[dict]:
                self.match_limit = limit
                return [make_match([{"fabid": "iron", "team": 0}])]

            def most_active_players(self, limit: int) -> list[dict]:
                self.player_limit = limit
                return [{"fabid": "iron", "steamUsername": "Iron", "matchesPlayed": 1}]

        client = FakeClient()

        result = sync_needys_stats(
            client,
            self.connection,
            match_limit=100,
            player_limit=200,
            active_window_days=30,
            active_min_matches=1,
        )

        self.assertEqual(client.match_limit, 100)
        self.assertEqual(client.player_limit, 200)
        self.assertEqual(result["matches"], 1)
        self.assertEqual(result["players"], 1)

    def test_active_skm_filter_counts_recent_matches_and_prunes_players(self) -> None:
        matches = [
            make_match(
                [{"fabid": "regular", "team": 0}, {"fabid": "guest", "team": 1}],
                match_key=f"recent-{index}",
                date=f"2026-07-{20 + index:02d} 12:00",
            )
            for index in range(5)
        ]
        matches.append(
            make_match(
                [{"fabid": "old", "team": 0}],
                match_key="old-match",
                date="2026-05-01 12:00",
            )
        )
        matches.append(
            make_match(
                [{"fabid": "other-mode", "team": 0}],
                match_key="other-mode",
                date="2026-07-24 12:00",
                gamemode="Frontline",
            )
        )
        upsert_matches(self.connection, matches)
        upsert_players(
            self.connection,
            [
                {"fabid": "regular", "steamUsername": "Regular"},
                {"fabid": "guest", "steamUsername": "Guest"},
                {"fabid": "old", "steamUsername": "Old"},
                {"fabid": "other-mode", "steamUsername": "Other"},
            ],
        )

        active = load_active_skm_player_counts(
            self.connection,
            window_days=30,
            min_matches=5,
        )
        pruned = prune_players(self.connection, active)

        self.assertEqual(active, {"guest": 5, "regular": 5})
        self.assertEqual(pruned, 2)
        self.assertEqual(
            {player["fabid"] for player in load_players(self.connection)},
            {"guest", "regular"},
        )
