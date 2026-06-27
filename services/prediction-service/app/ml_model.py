from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ml_features import FEATURE_NAMES, TrainingExample


MODEL_VERSION = "logistic-regression-v1"


@dataclass(frozen=True)
class LogisticMatchModel:
    feature_names: list[str]
    means: dict[str, float]
    scales: dict[str, float]
    weights: dict[str, float]
    intercept: float
    trained_at: str
    training_examples: int
    test_examples: int
    metrics: dict[str, Any]

    def predict_probability(self, features: dict[str, float]) -> float:
        logit = self.intercept
        for name in self.feature_names:
            value = (float(features.get(name, 0.0)) - self.means[name]) / self.scales[name]
            logit += self.weights[name] * value
        return sigmoid(logit)

    def explain(self, features: dict[str, float], limit: int = 5) -> list[dict[str, Any]]:
        contributions = []
        for name in self.feature_names:
            value = float(features.get(name, 0.0))
            standardized = (value - self.means[name]) / self.scales[name]
            contribution = self.weights[name] * standardized
            contributions.append(
                {
                    "feature": name,
                    "value": round(value, 4),
                    "contribution": round(contribution, 4),
                    "leansTeam": 0 if contribution >= 0 else 1,
                }
            )
        return sorted(contributions, key=lambda item: abs(item["contribution"]), reverse=True)[:limit]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": MODEL_VERSION,
            "featureNames": self.feature_names,
            "means": self.means,
            "scales": self.scales,
            "weights": self.weights,
            "intercept": self.intercept,
            "trainedAt": self.trained_at,
            "trainingExamples": self.training_examples,
            "testExamples": self.test_examples,
            "metrics": self.metrics,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "available": True,
            "version": MODEL_VERSION,
            "trainedAt": self.trained_at,
            "trainingExamples": self.training_examples,
            "testExamples": self.test_examples,
            "metrics": self.metrics,
            "topWeights": top_weights(self.weights),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LogisticMatchModel":
        return cls(
            feature_names=list(payload.get("featureNames") or FEATURE_NAMES),
            means={key: float(value) for key, value in payload.get("means", {}).items()},
            scales={key: float(value) for key, value in payload.get("scales", {}).items()},
            weights={key: float(value) for key, value in payload.get("weights", {}).items()},
            intercept=float(payload.get("intercept", 0.0)),
            trained_at=str(payload.get("trainedAt") or ""),
            training_examples=int(payload.get("trainingExamples") or 0),
            test_examples=int(payload.get("testExamples") or 0),
            metrics=dict(payload.get("metrics") or {}),
        )


def train_logistic_model(
    examples: list[TrainingExample],
    *,
    learning_rate: float = 0.08,
    iterations: int = 2800,
    l2: float = 0.002,
) -> LogisticMatchModel:
    if len(examples) < 10:
        raise ValueError("Need at least 10 completed matches to train the first ML model.")

    labels = [example.label for example in examples]
    if len(set(labels)) < 2:
        raise ValueError("Training data needs wins from both teams before ML can learn.")

    train_examples, test_examples = time_aware_split(examples)
    if len({example.label for example in train_examples}) < 2:
        train_examples = examples
        test_examples = []

    means, scales = fit_scaler(train_examples)
    weights = {name: 0.0 for name in FEATURE_NAMES}
    base_rate = clamp(sum(example.label for example in train_examples) / len(train_examples))
    intercept = math.log(base_rate / (1.0 - base_rate))

    for _ in range(iterations):
        gradients = {name: 0.0 for name in FEATURE_NAMES}
        intercept_gradient = 0.0

        for example in train_examples:
            logit = intercept
            standardized = standardize(example.features, means, scales)
            for name in FEATURE_NAMES:
                logit += weights[name] * standardized[name]

            error = sigmoid(logit) - example.label
            intercept_gradient += error
            for name in FEATURE_NAMES:
                gradients[name] += error * standardized[name]

        sample_count = len(train_examples)
        intercept -= learning_rate * (intercept_gradient / sample_count)
        for name in FEATURE_NAMES:
            gradient = (gradients[name] / sample_count) + l2 * weights[name]
            weights[name] -= learning_rate * gradient

    model = LogisticMatchModel(
        feature_names=list(FEATURE_NAMES),
        means=means,
        scales=scales,
        weights=weights,
        intercept=intercept,
        trained_at=datetime.now(timezone.utc).isoformat(),
        training_examples=len(train_examples),
        test_examples=len(test_examples),
        metrics={
            "train": evaluate_model(weights, intercept, means, scales, train_examples),
            "test": evaluate_model(weights, intercept, means, scales, test_examples)
            if test_examples
            else None,
        },
    )
    return model


def time_aware_split(examples: list[TrainingExample]) -> tuple[list[TrainingExample], list[TrainingExample]]:
    if len(examples) < 20:
        return examples, []
    test_count = max(1, int(len(examples) * 0.2))
    split_index = len(examples) - test_count
    return examples[:split_index], examples[split_index:]


def fit_scaler(examples: list[TrainingExample]) -> tuple[dict[str, float], dict[str, float]]:
    means = {}
    scales = {}
    for name in FEATURE_NAMES:
        values = [float(example.features.get(name, 0.0)) for example in examples]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        scale = math.sqrt(variance)
        means[name] = mean
        scales[name] = scale if scale > 0.000001 else 1.0
    return means, scales


def standardize(
    features: dict[str, float],
    means: dict[str, float],
    scales: dict[str, float],
) -> dict[str, float]:
    return {
        name: (float(features.get(name, 0.0)) - means[name]) / scales[name]
        for name in FEATURE_NAMES
    }


def evaluate_model(
    weights: dict[str, float],
    intercept: float,
    means: dict[str, float],
    scales: dict[str, float],
    examples: list[TrainingExample],
) -> dict[str, float | int]:
    if not examples:
        return {"examples": 0, "accuracy": 0.0, "logLoss": 0.0, "brier": 0.0}

    correct = 0
    log_loss = 0.0
    brier = 0.0
    for example in examples:
        standardized = standardize(example.features, means, scales)
        logit = intercept + sum(weights[name] * standardized[name] for name in FEATURE_NAMES)
        probability = clamp(sigmoid(logit))
        predicted = 1 if probability >= 0.5 else 0
        correct += 1 if predicted == example.label else 0
        log_loss += -(
            example.label * math.log(probability)
            + (1 - example.label) * math.log(1.0 - probability)
        )
        brier += (probability - example.label) ** 2

    count = len(examples)
    return {
        "examples": count,
        "accuracy": round(correct / count, 4),
        "logLoss": round(log_loss / count, 4),
        "brier": round(brier / count, 4),
    }


def save_model(model: LogisticMatchModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.as_dict(), indent=2), encoding="utf-8")


def load_model(path: Path) -> LogisticMatchModel | None:
    if not path.exists():
        return None
    return LogisticMatchModel.from_dict(json.loads(path.read_text(encoding="utf-8")))


def top_weights(weights: dict[str, float], limit: int = 5) -> list[dict[str, float | str]]:
    ranked = sorted(weights.items(), key=lambda item: abs(item[1]), reverse=True)
    return [
        {
            "feature": name,
            "weight": round(weight, 4),
            "leansTeam": 0 if weight >= 0 else 1,
        }
        for name, weight in ranked[:limit]
    ]


def clamp(value: float) -> float:
    return min(0.999999, max(0.000001, value))


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)
