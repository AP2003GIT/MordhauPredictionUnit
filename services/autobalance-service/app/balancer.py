from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Any


DEFAULT_RATING = 1000.0
RATING_SCALE = 180.0
MOVE_PENALTY = 0.0025
MAX_EXACT_ASSIGNMENTS = 200_000
MAX_PLAYERS = 32
TEAM_NAMES = {0: "Iron Company", 1: "Free Guard"}


class BalanceError(ValueError):
    """Raised when a roster cannot produce a balance preview."""


@dataclass(frozen=True)
class BalancePlayer:
    fabid: str
    name: str
    current_team: int
    rating: float
    matches: int
    effective_rating: float


@dataclass(frozen=True)
class Assignment:
    team_zero: frozenset[int]
    probability: float
    probability_gap: float
    move_count: int
    objective: float


def build_balance_preview(
    raw_players: list[dict[str, Any]],
    ratings: list[dict[str, Any]] | None = None,
    *,
    max_moves: int = 4,
    tolerance: float = 0.05,
) -> dict[str, Any]:
    if max_moves < 0:
        raise BalanceError("Maximum moves cannot be negative.")
    if not 0.0 <= tolerance <= 0.25:
        raise BalanceError("Balance tolerance must be between 0 and 0.25.")

    players = normalize_players(raw_players, ratings or [])
    if len(players) < 2:
        raise BalanceError("Need at least two active players across the two teams.")
    if len(players) > MAX_PLAYERS:
        raise BalanceError(f"Dry-run balancing supports at most {MAX_PLAYERS} active players.")

    current_team_zero = frozenset(
        index for index, player in enumerate(players) if player.current_team == 0
    )
    current = evaluate_assignment(players, current_team_zero)
    sizes_are_fair = abs(len(current_team_zero) - (len(players) - len(current_team_zero))) <= 1

    if sizes_are_fair and current.probability_gap <= tolerance:
        proposed = current
        algorithm = "no-change"
        evaluated_assignments = 1
        reason = "Current teams are already inside the configured fair-probability range."
    else:
        target_sizes = sorted({len(players) // 2, math.ceil(len(players) / 2)})
        exact_count = sum(math.comb(len(players), size) for size in target_sizes)
        if exact_count <= MAX_EXACT_ASSIGNMENTS:
            proposed, evaluated_assignments = find_exact_assignment(
                players,
                target_sizes,
                max_moves=max_moves,
            )
            algorithm = "exact-combinations"
        else:
            proposed, evaluated_assignments = find_local_assignment(
                players,
                current_team_zero,
                target_sizes,
                max_moves=max_moves,
            )
            algorithm = "move-limited-local-swap"

        if proposed.team_zero == current.team_zero:
            reason = "No allowed move set improves the current teams under the configured move limit."
        else:
            reason = (
                f"Recommend {proposed.move_count} move(s) to reduce the predicted win-probability "
                f"spread from {current.probability_gap:.1%} to {proposed.probability_gap:.1%}."
            )

    moves = build_moves(players, proposed.team_zero)
    should_apply = bool(moves) and proposed.probability_gap < current.probability_gap

    return {
        "status": "ok",
        "dryRun": True,
        "shouldApply": should_apply,
        "reason": reason,
        "playerCount": len(players),
        "algorithm": algorithm,
        "evaluatedAssignments": evaluated_assignments,
        "constraints": {
            "maxMoves": max_moves,
            "tolerance": round(tolerance, 4),
            "acceptableProbabilityRange": [
                round(0.5 - tolerance, 4),
                round(0.5 + tolerance, 4),
            ],
        },
        "current": assignment_payload(players, current),
        "proposed": assignment_payload(players, proposed),
        "moves": moves,
        "improvement": {
            "probabilitySpread": round(
                current.probability_gap - proposed.probability_gap,
                4,
            ),
        },
    }


def normalize_players(
    raw_players: list[dict[str, Any]],
    ratings: list[dict[str, Any]],
) -> list[BalancePlayer]:
    rating_catalog = {
        str(player.get("fabid") or "").strip(): player
        for player in ratings
        if isinstance(player, dict) and str(player.get("fabid") or "").strip()
    }
    normalized: list[BalancePlayer] = []
    seen: set[str] = set()

    for raw_player in raw_players:
        if not isinstance(raw_player, dict):
            continue
        fabid = str(raw_player.get("fabid") or "").strip()
        if not fabid or fabid in seen:
            continue
        team = to_int(raw_player.get("currentTeam", raw_player.get("team")), default=-1)
        if team not in (0, 1):
            continue

        profile = rating_catalog.get(fabid, {})
        rating = first_float(
            raw_player,
            ("displayRating", "rating"),
            default=first_float(profile, ("displayRating", "rating"), DEFAULT_RATING),
        )
        matches = first_int(
            raw_player,
            ("matches", "historicalMatches", "aggregateMatches"),
            default=first_int(profile, ("matches", "aggregateMatches"), 0),
        )
        reliability = matches / (matches + 10.0) if matches > 0 else 0.0
        effective_rating = DEFAULT_RATING + reliability * (rating - DEFAULT_RATING)
        name = str(
            raw_player.get("name")
            or raw_player.get("steamUsername")
            or raw_player.get("playername")
            or profile.get("name")
            or "Unknown"
        )

        normalized.append(
            BalancePlayer(
                fabid=fabid,
                name=name,
                current_team=team,
                rating=round(rating, 1),
                matches=matches,
                effective_rating=round(effective_rating, 3),
            )
        )
        seen.add(fabid)

    return normalized


def find_exact_assignment(
    players: list[BalancePlayer],
    target_sizes: list[int],
    *,
    max_moves: int,
) -> tuple[Assignment, int]:
    best: Assignment | None = None
    evaluated = 0
    indices = range(len(players))

    for target_size in target_sizes:
        for combination in itertools.combinations(indices, target_size):
            assignment = evaluate_assignment(players, frozenset(combination))
            if assignment.move_count > max_moves:
                continue
            evaluated += 1
            if best is None or assignment_key(assignment) < assignment_key(best):
                best = assignment

    current = evaluate_assignment(
        players,
        frozenset(index for index, player in enumerate(players) if player.current_team == 0),
    )
    return (best or current), evaluated


def find_local_assignment(
    players: list[BalancePlayer],
    current_team_zero: frozenset[int],
    target_sizes: list[int],
    *,
    max_moves: int,
) -> tuple[Assignment, int]:
    best = evaluate_assignment(players, current_team_zero)
    evaluated = 1

    for target_size in target_sizes:
        repaired, repair_evaluated = repair_team_size(
            players,
            current_team_zero,
            target_size,
            max_moves,
        )
        evaluated += repair_evaluated
        candidate, swap_evaluated = improve_with_swaps(players, repaired, max_moves)
        evaluated += swap_evaluated
        if assignment_key(candidate) < assignment_key(best):
            best = candidate

    return best, evaluated


def repair_team_size(
    players: list[BalancePlayer],
    initial_team_zero: frozenset[int],
    target_size: int,
    max_moves: int,
) -> tuple[Assignment, int]:
    team_zero = set(initial_team_zero)
    evaluated = 0

    while len(team_zero) != target_size:
        candidates = team_zero if len(team_zero) > target_size else set(range(len(players))) - team_zero
        best_step: Assignment | None = None
        for index in candidates:
            proposed = set(team_zero)
            if index in proposed:
                proposed.remove(index)
            else:
                proposed.add(index)
            assignment = evaluate_assignment(players, frozenset(proposed))
            evaluated += 1
            if assignment.move_count > max_moves:
                continue
            if best_step is None or assignment_key(assignment) < assignment_key(best_step):
                best_step = assignment
        if best_step is None:
            break
        team_zero = set(best_step.team_zero)

    return evaluate_assignment(players, frozenset(team_zero)), evaluated


def improve_with_swaps(
    players: list[BalancePlayer],
    initial: Assignment,
    max_moves: int,
) -> tuple[Assignment, int]:
    best = initial
    evaluated = 0

    for _ in range(32):
        next_best = best
        team_one = set(range(len(players))) - set(best.team_zero)
        for team_zero_index in best.team_zero:
            for team_one_index in team_one:
                proposed = set(best.team_zero)
                proposed.remove(team_zero_index)
                proposed.add(team_one_index)
                assignment = evaluate_assignment(players, frozenset(proposed))
                evaluated += 1
                if assignment.move_count > max_moves:
                    continue
                if assignment_key(assignment) < assignment_key(next_best):
                    next_best = assignment
        if next_best.team_zero == best.team_zero:
            break
        best = next_best

    return best, evaluated


def evaluate_assignment(
    players: list[BalancePlayer],
    team_zero: frozenset[int],
) -> Assignment:
    team_one = set(range(len(players))) - set(team_zero)
    if not team_zero or not team_one:
        probability = 1.0 if team_zero else 0.0
    else:
        average_zero = sum(players[index].effective_rating for index in team_zero) / len(team_zero)
        average_one = sum(players[index].effective_rating for index in team_one) / len(team_one)
        probability = sigmoid((average_zero - average_one) / RATING_SCALE)

    move_count = sum(
        1
        for index, player in enumerate(players)
        if (0 if index in team_zero else 1) != player.current_team
    )
    probability_gap = abs(probability - 0.5)
    size_gap = abs(len(team_zero) - len(team_one))
    objective = size_gap + probability_gap + MOVE_PENALTY * move_count
    return Assignment(
        team_zero=team_zero,
        probability=probability,
        probability_gap=probability_gap,
        move_count=move_count,
        objective=objective,
    )


def assignment_key(assignment: Assignment) -> tuple[float, int, tuple[int, ...]]:
    return (
        round(assignment.objective, 12),
        assignment.move_count,
        tuple(sorted(assignment.team_zero)),
    )


def assignment_payload(
    players: list[BalancePlayer],
    assignment: Assignment,
) -> dict[str, Any]:
    teams = []
    for team in (0, 1):
        indices = [
            index
            for index in range(len(players))
            if (index in assignment.team_zero) == (team == 0)
        ]
        average_rating = sum(players[index].effective_rating for index in indices) / len(indices)
        teams.append(
            {
                "team": team,
                "name": TEAM_NAMES[team],
                "size": len(indices),
                "averageRating": round(average_rating, 1),
                "probability": round(
                    assignment.probability if team == 0 else 1.0 - assignment.probability,
                    4,
                ),
                "players": [player_payload(players[index]) for index in indices],
            }
        )

    return {
        "team0Probability": round(assignment.probability, 4),
        "team1Probability": round(1.0 - assignment.probability, 4),
        "probabilitySpread": round(abs(2.0 * assignment.probability - 1.0), 4),
        "teams": teams,
    }


def build_moves(
    players: list[BalancePlayer],
    proposed_team_zero: frozenset[int],
) -> list[dict[str, Any]]:
    moves = []
    for index, player in enumerate(players):
        proposed_team = 0 if index in proposed_team_zero else 1
        if proposed_team == player.current_team:
            continue
        moves.append(
            {
                **player_payload(player),
                "fromTeam": player.current_team,
                "fromTeamName": TEAM_NAMES[player.current_team],
                "toTeam": proposed_team,
                "toTeamName": TEAM_NAMES[proposed_team],
            }
        )
    return sorted(moves, key=lambda move: (move["fromTeam"], -move["effectiveRating"], move["name"]))


def player_payload(player: BalancePlayer) -> dict[str, Any]:
    return {
        "fabid": player.fabid,
        "name": player.name,
        "rating": player.rating,
        "effectiveRating": round(player.effective_rating, 1),
        "matches": player.matches,
    }


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def first_float(payload: dict[str, Any], keys: tuple[str, ...], default: float) -> float:
    for key in keys:
        if key not in payload or payload[key] in (None, ""):
            continue
        try:
            return float(payload[key])
        except (TypeError, ValueError):
            continue
    return default


def first_int(payload: dict[str, Any], keys: tuple[str, ...], default: int) -> int:
    for key in keys:
        if key not in payload or payload[key] in (None, ""):
            continue
        try:
            return int(payload[key])
        except (TypeError, ValueError):
            continue
    return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
