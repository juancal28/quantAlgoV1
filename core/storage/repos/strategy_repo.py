"""Repository functions for strategy_versions table."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.storage.models import StrategyAuditLog, StrategyVersion


async def get_active_by_name(
    session: AsyncSession, name: str
) -> StrategyVersion | None:
    """Return the currently active version of a strategy, if any."""
    stmt = (
        select(StrategyVersion)
        .where(StrategyVersion.name == name, StrategyVersion.status == "active")
        .order_by(StrategyVersion.version.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_versions_by_name(
    session: AsyncSession, name: str
) -> list[StrategyVersion]:
    """Return all versions of a strategy ordered by version descending."""
    stmt = (
        select(StrategyVersion)
        .where(StrategyVersion.name == name)
        .order_by(StrategyVersion.version.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_version(
    session: AsyncSession, version: StrategyVersion
) -> StrategyVersion:
    """Insert a new strategy version."""
    session.add(version)
    await session.flush()
    return version


async def get_all_strategies(
    session: AsyncSession,
    status: str | None = None,
    limit: int = 50,
) -> list[StrategyVersion]:
    """Return strategies, optionally filtered by status."""
    stmt = select(StrategyVersion).order_by(StrategyVersion.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(StrategyVersion.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_version_by_strategy_and_id(
    session: AsyncSession, strategy_name: str, version_id_str: str
) -> StrategyVersion | None:
    """Fetch a specific version by strategy name and version ID string.

    Filters in Python to avoid SQLite UUID type mismatch issues.
    """
    versions = await get_versions_by_name(session, strategy_name)
    for v in versions:
        if str(v.id) == version_id_str:
            return v
    return None


async def count_activations_today(
    session: AsyncSession, strategy_name: str
) -> int:
    """Count how many times a strategy was approved today (UTC)."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    stmt = (
        select(func.count())
        .select_from(StrategyAuditLog)
        .where(
            StrategyAuditLog.strategy_name == strategy_name,
            StrategyAuditLog.action == "approved",
            StrategyAuditLog.timestamp >= today_start,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def update_status(
    session: AsyncSession,
    version_id: uuid.UUID,
    new_status: str,
    approved_by: str | None = None,
) -> StrategyVersion | None:
    """Update the status of a strategy version."""
    sv = await session.get(StrategyVersion, version_id)
    if sv is None:
        return None
    sv.status = new_status
    if approved_by:
        sv.approved_by = approved_by
    if new_status == "active":
        sv.activated_at = datetime.now(timezone.utc)
    await session.flush()
    return sv
