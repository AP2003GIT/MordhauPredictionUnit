from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("MPU_DATA_DIR", BASE_DIR / "data"))
DATABASE_PATH = Path(os.getenv("MPU_DATABASE_PATH", DATA_DIR / "mordhau_prediction.sqlite3"))

NEEDYS_BASE_URL = os.getenv("NEEDYS_BASE_URL", "https://needys-community.com")

