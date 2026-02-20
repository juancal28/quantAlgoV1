"""Repository functions for runs table."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.storage.models import Run


async def create_run(
    session: AsyncSession,
    run_type: str,
    details: dict | None = None,
) -> Run:
    """Create a new run record with status 'running'."""
    run = Run(
        run_type=run_type,
        status="running",
        details=details,
    )
    session.add(run)
    await session.flush()
    return run


async def complete_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    status: str = "ok",
    details: dict | None = None,
) -> Run | None:
    """Mark a run as completed (ok or fail)."""
    run = await session.get(Run, run_id)
    if run is None:
        return None
    run.status = status
    run.ended_at = datetime.now(timezone.utc)
    if details is not None:
        run.details = details
    await session.flush()
    return run


async def get_by_id(
    session: AsyncSession,
    run_id: uuid.UUID,
) -> Run | None:
    """Fetch a single run by primary key."""
    return await session.get(Run, run_id)


async def get_latest_by_type(
    session: AsyncSession,
    run_type: str,
) -> Run | None:
    """Return the most recent run of a given type."""
    stmt = (
        select(Run)
        .where(Run.run_type == run_type)
        .order_by(Run.started_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_recent(
    session: AsyncSession,
    limit: int = 20,
) -> list[Run]:
    """Return the most recent runs."""
    stmt = (
        select(Run)
        .order_by(Run.started_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
