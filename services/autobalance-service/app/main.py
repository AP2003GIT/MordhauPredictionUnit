from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .balancer import BalanceError, build_balance_preview
from .config import AUTOBALANCE_DRY_RUN, DATA_SERVICE_URL, PREDICTION_SERVICE_URL
from .service_client import JsonServiceClient, ServiceClientError


app = FastAPI(title="Mordhau Autobalance Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BalancePreviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    players: list[dict[str, Any]] | None = Field(default=None, max_length=32)
    max_moves: int = Field(default=4, alias="maxMoves", ge=0, le=16)
    tolerance: float = Field(default=0.05, ge=0.0, le=0.25)


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": "autobalance-service",
        "dryRun": AUTOBALANCE_DRY_RUN,
    }


@app.post("/balance/preview")
def preview_balance(request: BalancePreviewRequest) -> dict[str, Any]:
    source = "provided-roster"
    raw_players = request.players

    try:
        if raw_players is None:
            source = "live-scoreboard"
            scoreboard = JsonServiceClient(DATA_SERVICE_URL).get_json(
                "/scoreboard/current",
                {"save_snapshot": "true"},
            )
            raw_players = scoreboard.get("scoreboard", [])
            if not isinstance(raw_players, list) or not raw_players:
                raise HTTPException(
                    status_code=409,
                    detail="No live players are currently available for a balance preview.",
                )

        ratings_payload = JsonServiceClient(PREDICTION_SERVICE_URL).get_json(
            "/ratings",
            {"limit": 20000},
        )
    except ServiceClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    ratings = ratings_payload.get("players", [])
    try:
        preview = build_balance_preview(
            raw_players,
            ratings if isinstance(ratings, list) else [],
            max_moves=request.max_moves,
            tolerance=request.tolerance,
        )
    except BalanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    preview["source"] = source
    return preview


@app.post("/balance/apply")
def apply_balance() -> dict[str, Any]:
    raise HTTPException(
        status_code=409,
        detail=(
            "Team changes are disabled in the dry-run milestone. Review previews and configure "
            "an authenticated RCON connection before enabling apply."
        ),
    )
