"""Backtest endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db
from core.storage.repos import strategy_repo

router = APIRouter(prefix="/strategies", tags=["backtests"])


class BacktestRequest(BaseModel):
    start: str
    end: str


class BacktestMetrics(BaseModel):
    cagr: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    turnover: float
    avg_trade_return: float


class BacktestResponse(BaseModel):
    metrics: BacktestMetrics
    passed: bool


@router.post("/{name}/backtest", response_model=BacktestResponse)
async def run_backtest(
    name: str,
    body: BacktestRequest,
    session: AsyncSession = Depends(get_db),
) -> BacktestResponse:
    active = await strategy_repo.get_active_by_name(session, name)
    if active is None:
        raise HTTPException(status_code=404, detail=f"No active strategy for {name!r}")

    # Lazy import to avoid circular deps at module level
    from apps.mcp_server.schemas import RunBacktestInput
    from apps.mcp_server.tools.backtest import run_backtest_tool

    params = RunBacktestInput(
        definition_json=active.definition,
        start=body.start,
        end=body.end,
    )
    result = await run_backtest_tool(session, params)

    return BacktestResponse(
        metrics=BacktestMetrics(
            cagr=result.metrics.cagr,
            sharpe=result.metrics.sharpe,
            max_drawdown=result.metrics.max_drawdown,
            win_rate=result.metrics.win_rate,
            turnover=result.metrics.turnover,
            avg_trade_return=result.metrics.avg_trade_return,
        ),
        passed=result.passed,
    )
