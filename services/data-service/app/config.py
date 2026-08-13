from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("MPU_DATA_DIR", BASE_DIR / "data"))
DATABASE_PATH = Path(os.getenv("MPU_DATABASE_PATH", DATA_DIR / "mordhau_prediction.sqlite3"))

NEEDYS_BASE_URL = os.getenv("NEEDYS_BASE_URL", "https://www.needys-community.com")


def positive_int_from_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def at_least_one_int_from_env(name: str, default: int) -> int:
    return max(1, positive_int_from_env(name, default))


AUTOSYNC_INTERVAL_SECONDS = positive_int_from_env("MPU_AUTOSYNC_INTERVAL_SECONDS", 30)
AUTOSYNC_MATCH_LIMIT = positive_int_from_env("MPU_AUTOSYNC_MATCH_LIMIT", 100)
AUTOSYNC_PLAYER_LIMIT = positive_int_from_env("MPU_AUTOSYNC_PLAYER_LIMIT", 200)
ACTIVE_SKM_WINDOW_DAYS = at_least_one_int_from_env("MPU_ACTIVE_SKM_WINDOW_DAYS", 30)
ACTIVE_SKM_MIN_MATCHES = at_least_one_int_from_env("MPU_ACTIVE_SKM_MIN_MATCHES", 5)
