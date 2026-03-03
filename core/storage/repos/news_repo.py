"""Repository functions for news_documents table."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.storage.models import NewsDocument


async def get_by_id(session: AsyncSession, doc_id: uuid.UUID) -> NewsDocument | None:
    """Fetch a single news document by primary key."""
    return await session.get(NewsDocument, doc_id)


async def get_by_content_hash(session: AsyncSession, content_hash: str) -> NewsDocument | None:
    """Fetch a news document by its content SHA-256 hash."""
    stmt = select(NewsDocument).where(NewsDocument.content_hash == content_hash)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_source_url(session: AsyncSession, source_url: str) -> NewsDocument | None:
    """Fetch a news document by its source URL."""
    stmt = select(NewsDocument).where(NewsDocument.source_url == source_url)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create(session: AsyncSession, doc: NewsDocument) -> NewsDocument:
    """Insert a new news document and flush to obtain its ID."""
    session.add(doc)
    await session.flush()
    return doc


async def count_recent(
    session: AsyncSession,
    minutes: int = 120,
) -> int:
    """Count documents ingested within the given time window."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    stmt = select(func.count(NewsDocument.id)).where(
        NewsDocument.fetched_at >= cutoff
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def get_recent(
    session: AsyncSession,
    minutes: int = 120,
    limit: int = 50,
    by_published: bool = False,
) -> list[NewsDocument]:
    """Return the most recent news documents within the given time window.

    Args:
        by_published: If True, filter/sort by published_at (for signal evaluation
            where stale news should not drive trades). If False, use fetched_at
            (for API display of recently ingested articles).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    col = NewsDocument.published_at if by_published else NewsDocument.fetched_at
    stmt = (
        select(NewsDocument)
        .where(col >= cutoff)
        .order_by(col.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_old_documents(
    session: AsyncSession,
    days: int,
    limit: int = 500,
) -> list[NewsDocument]:
    """Return documents older than *days* days, ordered oldest first."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(NewsDocument)
        .where(NewsDocument.fetched_at < cutoff)
        .order_by(NewsDocument.fetched_at.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_by_ids(
    session: AsyncSession,
    doc_ids: list[uuid.UUID],
) -> int:
    """Bulk delete news documents by primary key. Returns count deleted."""
    if not doc_ids:
        return 0
    stmt = delete(NewsDocument).where(NewsDocument.id.in_(doc_ids))
    result = await session.execute(stmt)
    return result.rowcount
