"""Run endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db
from core.logging import get_logger
from core.storage.repos import run_repo

logger = get_logger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])


class RunResponse(BaseModel):
    id: str
    run_type: str
    started_at: datetime
    ended_at: datetime | None = None
    status: str
    details: dict[str, Any] | None = None


class NewsCycleTriggerResponse(BaseModel):
    run_id: str
    status: str


@router.get("/recent", response_model=list[RunResponse])
async def get_recent_runs(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> list[RunResponse]:
    runs = await run_repo.get_recent(session, limit=limit)
    return [
        RunResponse(
            id=str(r.id),
            run_type=r.run_type,
            started_at=r.started_at,
            ended_at=r.ended_at,
            status=r.status,
            details=r.details,
        )
        for r in runs
    ]


@router.post("/news_cycle", response_model=NewsCycleTriggerResponse)
async def trigger_news_cycle(
    session: AsyncSession = Depends(get_db),
) -> NewsCycleTriggerResponse:
    run = await run_repo.create_run(session, run_type="ingest")
    await session.commit()
    run_id_str = str(run.id)

    try:
        from apps.scheduler.jobs import run_news_cycle

        run_news_cycle.delay(run_id_str)
        status = "dispatched"
    except Exception:
        logger.warning("Celery unavailable, news_cycle not dispatched", exc_info=True)
        status = "failed"

    return NewsCycleTriggerResponse(run_id=run_id_str, status=status)
