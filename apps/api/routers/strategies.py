"""Strategy endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db
from core.agent.approval import approve_strategy, deactivate_strategy
from core.storage.repos import strategy_repo

router = APIRouter(prefix="/strategies", tags=["strategies"])


class StrategyVersionResponse(BaseModel):
    id: str
    name: str
    version: int
    status: str
    definition: dict[str, Any]
    created_at: datetime
    activated_at: datetime | None = None
    approved_by: str | None = None
    reason: str
    backtest_metrics: dict[str, Any] | None = None


class DeactivateResponse(BaseModel):
    strategy_version_id: str
    status: str
    name: str


class ApproveResponse(BaseModel):
    strategy_version_id: str
    status: str
    approved_by: str


def _to_response(v) -> StrategyVersionResponse:
    return StrategyVersionResponse(
        id=str(v.id),
        name=v.name,
        version=v.version,
        status=v.status,
        definition=v.definition,
        created_at=v.created_at,
        activated_at=v.activated_at,
        approved_by=v.approved_by,
        reason=v.reason,
        backtest_metrics=v.backtest_metrics,
    )


@router.get("", response_model=list[StrategyVersionResponse])
async def list_strategies(
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> list[StrategyVersionResponse]:
    versions = await strategy_repo.get_all_strategies(session, status=status)
    return [_to_response(v) for v in versions]


@router.get("/{name}/active", response_model=StrategyVersionResponse)
async def get_active_strategy(
    name: str,
    session: AsyncSession = Depends(get_db),
) -> StrategyVersionResponse:
    active = await strategy_repo.get_active_by_name(session, name)
    if active is None:
        raise HTTPException(status_code=404, detail=f"No active version for {name!r}")
    return _to_response(active)


@router.get("/{name}/versions", response_model=list[StrategyVersionResponse])
async def list_versions(
    name: str,
    session: AsyncSession = Depends(get_db),
) -> list[StrategyVersionResponse]:
    versions = await strategy_repo.get_versions_by_name(session, name)
    if not versions:
        raise HTTPException(status_code=404, detail=f"No versions found for {name!r}")
    return [_to_response(v) for v in versions]


@router.post("/{name}/approve/{version_id}", response_model=ApproveResponse)
async def approve_version(
    name: str,
    version_id: str,
    session: AsyncSession = Depends(get_db),
) -> ApproveResponse:
    try:
        activated = await approve_strategy(session, name, version_id)
        await session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ApproveResponse(
        strategy_version_id=str(activated.id),
        status=activated.status,
        approved_by=activated.approved_by or "human",
    )


@router.post("/{name}/deactivate", response_model=DeactivateResponse)
async def deactivate_version(
    name: str,
    session: AsyncSession = Depends(get_db),
) -> DeactivateResponse:
    try:
        archived = await deactivate_strategy(
            session, name, reason="manual deactivation", trigger="human"
        )
        await session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return DeactivateResponse(
        strategy_version_id=str(archived.id),
        status=archived.status,
        name=archived.name,
    )
