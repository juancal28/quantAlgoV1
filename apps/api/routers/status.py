"""System status endpoint (richer than /health)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db
from apps.mcp_server.schemas import SystemHealthInput
from apps.mcp_server.tools.monitoring import get_system_health

router = APIRouter(tags=["status"])


class StatusResponse(BaseModel):
    trading_mode: str
    paper_guard: bool
    market_open: bool
    last_ingest_run: dict[str, Any] | None = None
    news_count_last_2h: int
    strategy_counts: dict[str, int]
    services: dict[str, str]


@router.get("/status", response_model=StatusResponse)
async def system_status(
    session: AsyncSession = Depends(get_db),
) -> StatusResponse:
    result = await get_system_health(session, SystemHealthInput())
    return StatusResponse(
        trading_mode=result.trading_mode,
        paper_guard=result.paper_guard,
        market_open=result.market_open,
        last_ingest_run=result.last_ingest_run,
        news_count_last_2h=result.news_count_last_2h,
        strategy_counts=result.strategy_counts,
        services=result.services,
    )
