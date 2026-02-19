"""Repository functions for news_documents table."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
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
) -> list[NewsDocument]:
    """Return the most recent news documents within the given time window."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    stmt = (
        select(NewsDocument)
        .where(NewsDocument.published_at >= cutoff)
        .order_by(NewsDocument.published_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
