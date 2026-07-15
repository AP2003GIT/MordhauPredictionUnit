from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .config import DATA_DIR, DATABASE_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_key TEXT PRIMARY KEY,
    map TEXT,
    gamemode TEXT,
    duration TEXT,
    match_date TEXT,
    iron_company_score INTEGER,
    free_guard_score INTEGER,
    winner_team INTEGER,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_matches (
    match_key TEXT NOT NULL,
    fabid TEXT NOT NULL,
    playername TEXT,
    steam_username TEXT,
    steam_id64 TEXT,
    kills INTEGER DEFAULT 0,
    deaths INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    fd INTEGER DEFAULT 0,
    damage INTEGER DEFAULT 0,
    adr INTEGER DEFAULT 0,
    team INTEGER NOT NULL,
    PRIMARY KEY (match_key, fabid),
    FOREIGN KEY (match_key) REFERENCES matches(match_key)
);

CREATE TABLE IF NOT EXISTS players (
    fabid TEXT PRIMARY KEY,
    steam_username TEXT,
    steam_avatar TEXT,
    matches_played INTEGER DEFAULT 0,
    total_kills INTEGER DEFAULT 0,
    total_deaths INTEGER DEFAULT 0,
    total_assists INTEGER DEFAULT 0,
    kd REAL DEFAULT 0,
    playtime_hours REAL DEFAULT 0,
    last_match_time TEXT,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scoreboard_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT,
    match_key TEXT,
    map TEXT,
    gamemode TEXT,
    raw_json TEXT NOT NULL
);
"""


def connect(db_path: Path = DATABASE_PATH) -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    connection.commit()


def determine_winner(match: dict[str, Any]) -> int | None:
    iron_score = _to_int(match.get("iron_company_score"))
    free_score = _to_int(match.get("free_guard_score"))

    if iron_score is None or free_score is None or iron_score == free_score:
        return None

    return 0 if iron_score > free_score else 1


def upsert_matches(connection: sqlite3.Connection, matches: Iterable[dict[str, Any]]) -> int:
    init_db(connection)
    inserted_or_updated = 0

    for match in matches:
        match_key = str(match.get("match_key") or "").strip()
        if not match_key:
            continue

        winner_team = determine_winner(match)
        connection.execute(
            """
            INSERT INTO matches (
                match_key, map, gamemode, duration, match_date,
                iron_company_score, free_guard_score, winner_team, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_key) DO UPDATE SET
                map = excluded.map,
                gamemode = excluded.gamemode,
                duration = excluded.duration,
                match_date = excluded.match_date,
                iron_company_score = excluded.iron_company_score,
                free_guard_score = excluded.free_guard_score,
                winner_team = excluded.winner_team,
                raw_json = excluded.raw_json
            """,
            (
                match_key,
                match.get("map"),
                match.get("gamemode"),
                match.get("duration"),
                match.get("date"),
                _to_int(match.get("iron_company_score")),
                _to_int(match.get("free_guard_score")),
                winner_team,
                json.dumps(match, separators=(",", ":")),
            ),
        )

        # Treat the incoming match as the complete latest representation. Without
        # clearing prior rows, corrected upstream payloads leave removed players
        # in the normalized table even though raw_json has already been replaced.
        connection.execute("DELETE FROM player_matches WHERE match_key = ?", (match_key,))

        players = match.get("players", [])
        if isinstance(players, list):
            for player in players:
                if isinstance(player, dict):
                    upsert_player_match(connection, match_key, player)

        inserted_or_updated += 1

    connection.commit()
    return inserted_or_updated


def upsert_player_match(
    connection: sqlite3.Connection,
    match_key: str,
    player: dict[str, Any],
) -> None:
    fabid = str(player.get("fabid") or "").strip()
    if not fabid:
        return

    team = _to_int(player.get("team"))
    if team not in (0, 1):
        return

    connection.execute(
        """
        INSERT INTO player_matches (
            match_key, fabid, playername, steam_username, steam_id64,
            kills, deaths, assists, fd, damage, adr, team
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_key, fabid) DO UPDATE SET
            playername = excluded.playername,
            steam_username = excluded.steam_username,
            steam_id64 = excluded.steam_id64,
            kills = excluded.kills,
            deaths = excluded.deaths,
            assists = excluded.assists,
            fd = excluded.fd,
            damage = excluded.damage,
            adr = excluded.adr,
            team = excluded.team
        """,
        (
            match_key,
            fabid,
            player.get("playername"),
            player.get("steamUsername"),
            player.get("steamId64"),
            _to_int(player.get("kills"), default=0),
            _to_int(player.get("deaths"), default=0),
            _to_int(player.get("assists"), default=0),
            _to_int(player.get("fd"), default=0),
            _to_int(player.get("dmg"), default=0),
            _to_int(player.get("adr"), default=0),
            team,
        ),
    )


def save_scoreboard_snapshot(connection: sqlite3.Connection, payload: dict[str, Any]) -> None:
    init_db(connection)
    server = payload.get("server") if isinstance(payload.get("server"), dict) else {}
    connection.execute(
        """
        INSERT INTO scoreboard_snapshots (captured_at, match_key, map, gamemode, raw_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            payload.get("capturedAt") or payload.get("timestamp"),
            payload.get("match_key") or payload.get("matchKey"),
            server.get("Map") or payload.get("map"),
            server.get("GameMode") or payload.get("gamemode"),
            json.dumps(payload, separators=(",", ":")),
        ),
    )
    connection.commit()


def upsert_players(connection: sqlite3.Connection, players: Iterable[dict[str, Any]]) -> int:
    init_db(connection)
    inserted_or_updated = 0

    for player in players:
        fabid = str(player.get("fabid") or "").strip()
        if not fabid:
            continue

        connection.execute(
            """
            INSERT INTO players (
                fabid, steam_username, steam_avatar, matches_played,
                total_kills, total_deaths, total_assists, kd,
                playtime_hours, last_match_time, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fabid) DO UPDATE SET
                steam_username = excluded.steam_username,
                steam_avatar = excluded.steam_avatar,
                matches_played = excluded.matches_played,
                total_kills = excluded.total_kills,
                total_deaths = excluded.total_deaths,
                total_assists = excluded.total_assists,
                kd = excluded.kd,
                playtime_hours = excluded.playtime_hours,
                last_match_time = excluded.last_match_time,
                raw_json = excluded.raw_json
            """,
            (
                fabid,
                player.get("steamUsername"),
                player.get("steamAvatar"),
                _to_int(player.get("matchesPlayed"), default=0),
                _to_int(player.get("totalKills"), default=0),
                _to_int(player.get("totalDeaths"), default=0),
                _to_int(player.get("totalAssists"), default=0),
                _to_float(player.get("kd"), default=0.0),
                _to_float(player.get("playtimeHours"), default=0.0),
                player.get("lastMatchTime"),
                json.dumps(player, separators=(",", ":")),
            ),
        )
        inserted_or_updated += 1

    connection.commit()
    return inserted_or_updated


def load_history_matches(
    connection: sqlite3.Connection,
    limit: int = 9999,
    ascending: bool = True,
) -> list[dict[str, Any]]:
    init_db(connection)
    direction = "ASC" if ascending else "DESC"
    rows = connection.execute(
        f"""
        SELECT raw_json
        FROM matches
        WHERE winner_team IN (0, 1)
        ORDER BY match_date {direction}, match_key {direction}
        LIMIT ?
        """,
        (limit,),
    )
    return [json.loads(row["raw_json"]) for row in rows]


def load_players(connection: sqlite3.Connection, limit: int = 20000) -> list[dict[str, Any]]:
    init_db(connection)
    rows = connection.execute(
        """
        SELECT raw_json
        FROM players
        ORDER BY matches_played DESC, steam_username ASC
        LIMIT ?
        """,
        (limit,),
    )
    return [json.loads(row["raw_json"]) for row in rows]


def database_stats(connection: sqlite3.Connection) -> dict[str, int]:
    init_db(connection)
    match_count = connection.execute("SELECT COUNT(*) AS count FROM matches").fetchone()["count"]
    player_match_count = connection.execute(
        "SELECT COUNT(*) AS count FROM player_matches"
    ).fetchone()["count"]
    player_count = connection.execute("SELECT COUNT(*) AS count FROM players").fetchone()["count"]
    snapshot_count = connection.execute(
        "SELECT COUNT(*) AS count FROM scoreboard_snapshots"
    ).fetchone()["count"]
    return {
        "matches": int(match_count),
        "playerMatches": int(player_match_count),
        "players": int(player_count),
        "scoreboardSnapshots": int(snapshot_count),
    }


def _to_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
