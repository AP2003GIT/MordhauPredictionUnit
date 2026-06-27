from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ml_features import build_team_feature_differences, build_training_dataset  # noqa: E402
from app.ml_model import train_logistic_model  # noqa: E402


def make_match(index: int, winner: int) -> dict:
    return {
        "match_key": f"match-{index}",
        "date": f"2026-01-{index + 1:02d} 12:00",
        "iron_company_score": 7 if winner == 0 else 3,
        "free_guard_score": 3 if winner == 0 else 7,
        "players": [
            {"fabid": "strong-a", "steamUsername": "Strong A", "team": 0, "kills": 10, "deaths": 3, "assists": 2, "dmg": 1000, "adr": 100},
            {"fabid": "strong-b", "steamUsername": "Strong B", "team": 0, "kills": 8, "deaths": 4, "assists": 3, "dmg": 900, "adr": 90},
            {"fabid": "weak-a", "steamUsername": "Weak A", "team": 1, "kills": 3, "deaths": 9, "assists": 1, "dmg": 420, "adr": 42},
            {"fabid": "weak-b", "steamUsername": "Weak B", "team": 1, "kills": 2, "deaths": 10, "assists": 1, "dmg": 390, "adr": 39},
        ],
    }


def main() -> None:
    matches = [make_match(index, 0 if index % 5 else 1) for index in range(30)]
    dataset = build_training_dataset(matches)
    model = train_logistic_model(dataset.examples, iterations=500)
    features = build_team_feature_differences(
        {
            0: [{"fabid": "strong-a"}, {"fabid": "strong-b"}],
            1: [{"fabid": "weak-a"}, {"fabid": "weak-b"}],
        },
        dataset.final_ratings,
    )
    probability = model.predict_probability(features)
    assert probability > 0.5
    print({"ml": "ok", "examples": len(dataset.examples), "team0Probability": round(probability, 4)})


if __name__ == "__main__":
    main()
