"""Scheduler pause/resume endpoints."""

from __future__ import annotations

import redis
from fastapi import APIRouter
from pydantic import BaseModel

from core.config import get_settings

router = APIRouter(prefix="/scheduler", tags=["scheduler"])

PAUSE_KEY = "scheduler:paused"


def _redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().REDIS_URL)


class SchedulerStatusResponse(BaseModel):
    paused: bool


@router.get("/status", response_model=SchedulerStatusResponse)
async def scheduler_status() -> SchedulerStatusResponse:
    """Check whether the scheduler is paused."""
    return SchedulerStatusResponse(paused=bool(_redis().exists(PAUSE_KEY)))


@router.post("/pause", response_model=SchedulerStatusResponse)
async def pause_scheduler() -> SchedulerStatusResponse:
    """Pause all scheduled tasks (news cycle, trade ticks, etc.)."""
    _redis().set(PAUSE_KEY, "1")
    return SchedulerStatusResponse(paused=True)


@router.post("/resume", response_model=SchedulerStatusResponse)
async def resume_scheduler() -> SchedulerStatusResponse:
    """Resume all scheduled tasks."""
    _redis().delete(PAUSE_KEY)
    return SchedulerStatusResponse(paused=False)
