from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402
from app.predictor import predict_current_match  # noqa: E402
from app.ratings import PlayerRating  # noqa: E402


def main() -> None:
    payload = {
        "scoreboard": [
            {"fabid": "a", "steamUsername": "Strong A", "team": 0, "kills": 3, "deaths": 1},
            {"fabid": "b", "steamUsername": "Strong B", "team": 0, "kills": 2, "deaths": 1},
            {"fabid": "c", "steamUsername": "Weak C", "team": 1, "kills": 0, "deaths": 3},
            {"fabid": "d", "steamUsername": "Weak D", "team": 1, "kills": 1, "deaths": 3},
        ],
        "iron_company_score": 2,
        "free_guard_score": 0,
    }
    ratings = {
        "a": PlayerRating(fabid="a", name="Strong A", rating=1180, matches=20, wins=14),
        "b": PlayerRating(fabid="b", name="Strong B", rating=1140, matches=18, wins=12),
        "c": PlayerRating(fabid="c", name="Weak C", rating=940, matches=12, wins=4),
        "d": PlayerRating(fabid="d", name="Weak D", rating=920, matches=10, wins=3),
    }

    prediction = predict_current_match(payload, ratings).as_dict()
    assert prediction["status"] == "ok"
    assert prediction["teams"][0]["probability"] > prediction["teams"][1]["probability"]

    print({"service": app.title, "prediction": "ok"})


if __name__ == "__main__":
    main()

