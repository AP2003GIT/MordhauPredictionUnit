from __future__ import annotations

import sqlite3

from .needys_client import NeedysClient
from .storage import database_stats, upsert_matches, upsert_players


def sync_needys_stats(
    client: NeedysClient,
    connection: sqlite3.Connection,
    *,
    match_limit: int,
    player_limit: int,
) -> dict[str, int]:
    matches = client.recent_matches(limit=match_limit)
    players = client.most_active_players(limit=player_limit)
    matches_stored = upsert_matches(connection, matches)
    players_stored = upsert_players(connection, players)
    stats = database_stats(connection)

    return {
        "matchesFetched": len(matches),
        "matchesStored": matches_stored,
        "playersFetched": len(players),
        "playersStored": players_stored,
        **stats,
    }
