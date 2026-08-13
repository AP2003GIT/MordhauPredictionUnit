from __future__ import annotations

import os
from pathlib import Path


DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://127.0.0.1:8001")
BASE_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = Path(os.getenv("MPU_MODEL_DIR", BASE_DIR / "data"))
MODEL_PATH = Path(os.getenv("MPU_MODEL_PATH", MODEL_DIR / "match_model.json"))


def positive_int_from_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


ACTIVE_SKM_WINDOW_DAYS = positive_int_from_env("MPU_ACTIVE_SKM_WINDOW_DAYS", 30)
ACTIVE_SKM_MIN_MATCHES = positive_int_from_env("MPU_ACTIVE_SKM_MIN_MATCHES", 5)

TEAM_NAMES = {
    0: "Iron Company",
    1: "Free Guard",
}
