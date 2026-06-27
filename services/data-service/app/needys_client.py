from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import NEEDYS_BASE_URL


class NeedysApiError(RuntimeError):
    """Raised when the Needys API cannot be reached or parsed."""


@dataclass(frozen=True)
class NeedysClient:
    base_url: str = NEEDYS_BASE_URL
    timeout_seconds: int = 20

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.base_url}{path}{query}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "MordhauPredictionUnit/0.1 data-service",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except OSError as exc:
            raise NeedysApiError(f"Could not fetch {url}: {exc}") from exc

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise NeedysApiError(f"Needys returned invalid JSON for {url}") from exc

        if not isinstance(data, dict):
            raise NeedysApiError(f"Needys returned unexpected payload for {url}")

        return data

    def recent_matches(self, limit: int = 9999) -> list[dict[str, Any]]:
        payload = self.get_json("/api/matches/recent-global", {"limit": limit})
        matches = payload.get("matches", [])
        return matches if isinstance(matches, list) else []

    def dashboard_scoreboard(self) -> dict[str, Any]:
        return self.get_json("/api/dashboard/scoreboard")

