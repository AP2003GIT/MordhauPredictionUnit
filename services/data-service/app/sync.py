from __future__ import annotations

import sqlite3

from .needys_client import NeedysClient
from .storage import (
    database_stats,
    load_active_skm_player_counts,
    prune_players,
    upsert_matches,
    upsert_players,
)


def sync_needys_stats(
    client: NeedysClient,
    connection: sqlite3.Connection,
    *,
    match_limit: int,
    player_limit: int,
    active_window_days: int,
    active_min_matches: int,
) -> dict[str, int]:
    matches = client.recent_matches(limit=match_limit)
    players = client.most_active_players(limit=player_limit)
    matches_stored = upsert_matches(connection, matches)
    active_counts = load_active_skm_player_counts(
        connection,
        window_days=active_window_days,
        min_matches=active_min_matches,
    )
    active_players = [
        player
        for player in players
        if str(player.get("fabid") or "").strip() in active_counts
    ]
    players_stored = upsert_players(connection, active_players)
    players_pruned = prune_players(connection, active_counts)
    stats = database_stats(connection)

    return {
        "matchesFetched": len(matches),
        "matchesStored": matches_stored,
        "playersFetched": len(players),
        "playersEligible": len(active_players),
        "playersStored": players_stored,
        "playersPruned": players_pruned,
        "activeSkmPlayers": len(active_counts),
        **stats,
    }
