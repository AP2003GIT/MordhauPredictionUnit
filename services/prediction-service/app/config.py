from __future__ import annotations

import os
from pathlib import Path


DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://127.0.0.1:8001")
BASE_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = Path(os.getenv("MPU_MODEL_DIR", BASE_DIR / "data"))
MODEL_PATH = Path(os.getenv("MPU_MODEL_PATH", MODEL_DIR / "match_model.json"))

TEAM_NAMES = {
    0: "Iron Company",
    1: "Free Guard",
}
