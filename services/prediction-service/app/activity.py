from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any


def skm_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        match
        for match in matches
        if str(match.get("gamemode") or "").strip().casefold() in {"skirmish", "skm"}
    ]


def active_skm_player_counts(
    matches: list[dict[str, Any]],
    *,
    window_days: int = 30,
    min_matches: int = 5,
) -> dict[str, int]:
    dated_matches = [
        (parsed, match)
        for match in skm_matches(matches)
        if (parsed := parse_match_date(match.get("date"))) is not None
    ]
    if not dated_matches:
        return {}

    newest = max(parsed for parsed, _ in dated_matches)
    cutoff = newest - timedelta(days=max(1, window_days))
    appearances: Counter[str] = Counter()

    for parsed, match in dated_matches:
        if parsed < cutoff:
            continue
        participants = match.get("players", [])
        if not isinstance(participants, list):
            continue
        match_fabids = {
            str(player.get("fabid") or "").strip()
            for player in participants
            if isinstance(player, dict) and str(player.get("fabid") or "").strip()
        }
        appearances.update(match_fabids)

    threshold = max(1, min_matches)
    return {fabid: count for fabid, count in appearances.items() if count >= threshold}


def parse_match_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
