"""Autonomous mode endpoints — auto-approve strategies and trade without human input."""

from __future__ import annotations

import redis
from fastapi import APIRouter
from pydantic import BaseModel

from core.config import get_settings

router = APIRouter(prefix="/autonomous", tags=["autonomous"])

AUTONOMOUS_KEY = "autonomous:enabled"


def _redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().REDIS_URL)


class AutonomousStatusResponse(BaseModel):
    enabled: bool


@router.get("/status", response_model=AutonomousStatusResponse)
async def autonomous_status() -> AutonomousStatusResponse:
    """Check whether autonomous mode is enabled."""
    return AutonomousStatusResponse(enabled=bool(_redis().exists(AUTONOMOUS_KEY)))


@router.post("/enable", response_model=AutonomousStatusResponse)
async def enable_autonomous() -> AutonomousStatusResponse:
    """Enable autonomous mode: auto-approve all pending strategies immediately and trade."""
    _redis().set(AUTONOMOUS_KEY, "1")
    return AutonomousStatusResponse(enabled=True)


@router.post("/disable", response_model=AutonomousStatusResponse)
async def disable_autonomous() -> AutonomousStatusResponse:
    """Disable autonomous mode: require manual approval for strategies."""
    _redis().delete(AUTONOMOUS_KEY)
    return AutonomousStatusResponse(enabled=False)
