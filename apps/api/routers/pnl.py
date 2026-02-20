"""PnL endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db
from core.storage.repos import pnl_repo

router = APIRouter(prefix="/pnl", tags=["pnl"])


class PnlSnapshotResponse(BaseModel):
    date: date
    realized_pnl: float
    unrealized_pnl: float
    gross_exposure: float
    peak_pnl: float
    positions: dict[str, Any] | None = None


@router.get("/daily", response_model=list[PnlSnapshotResponse])
async def get_daily_pnl(
    strategy: str = Query(..., description="Strategy name"),
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_db),
) -> list[PnlSnapshotResponse]:
    snapshots = await pnl_repo.get_daily_snapshots(
        session, strategy_name=strategy, limit=days
    )
    return [
        PnlSnapshotResponse(
            date=s.snapshot_date,
            realized_pnl=float(s.realized_pnl),
            unrealized_pnl=float(s.unrealized_pnl),
            gross_exposure=float(s.gross_exposure),
            peak_pnl=float(s.peak_pnl),
            positions=s.positions,
        )
        for s in snapshots
    ]
