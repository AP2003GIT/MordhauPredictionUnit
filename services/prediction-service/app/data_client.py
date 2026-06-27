from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import DATA_SERVICE_URL


class DataServiceError(RuntimeError):
    """Raised when the data service cannot be reached or parsed."""


@dataclass(frozen=True)
class DataServiceClient:
    base_url: str = DATA_SERVICE_URL
    timeout_seconds: int = 20

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def post_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", path, params=params)

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.base_url}{path}{query}"
        request = Request(
            url,
            method=method,
            headers={
                "Accept": "application/json",
                "User-Agent": "MordhauPredictionUnit/0.1 prediction-service",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except OSError as exc:
            raise DataServiceError(f"Could not reach data service at {url}: {exc}") from exc

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise DataServiceError(f"Data service returned invalid JSON for {url}") from exc

        if not isinstance(data, dict):
            raise DataServiceError(f"Data service returned unexpected payload for {url}")

        return data

