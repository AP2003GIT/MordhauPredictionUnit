from __future__ import annotations

import os


DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://127.0.0.1:8001")
PREDICTION_SERVICE_URL = os.getenv("PREDICTION_SERVICE_URL", "http://127.0.0.1:8002")
AUTOBALANCE_DRY_RUN = os.getenv("AUTOBALANCE_DRY_RUN", "true").lower() not in {
    "0",
    "false",
    "no",
}
