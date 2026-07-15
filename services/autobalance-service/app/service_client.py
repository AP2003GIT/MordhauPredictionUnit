from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ServiceClientError(RuntimeError):
    """Raised when a local MPU service cannot be reached or parsed."""


@dataclass(frozen=True)
class JsonServiceClient:
    base_url: str
    timeout_seconds: int = 20

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.base_url}{path}{query}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "MordhauPredictionUnit/0.1 autobalance-service",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except OSError as exc:
            raise ServiceClientError(f"Could not reach {url}: {exc}") from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ServiceClientError(f"Service returned invalid JSON for {url}") from exc

        if not isinstance(payload, dict):
            raise ServiceClientError(f"Service returned an unexpected payload for {url}")
        return payload
