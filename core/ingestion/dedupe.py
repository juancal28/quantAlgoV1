"""Deduplication logic using SHA-256 content hashing."""

from __future__ import annotations

import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from core.ingestion.normalize import normalize_content
from core.storage.repos import news_repo


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of normalized content."""
    normalized = normalize_content(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def is_duplicate_url(session: AsyncSession, source_url: str) -> bool:
    """Check if a document with this URL already exists."""
    existing = await news_repo.get_by_source_url(session, source_url)
    return existing is not None


async def is_duplicate_content(session: AsyncSession, content: str) -> bool:
    """Check if a document with this content hash already exists."""
    content_hash = compute_content_hash(content)
    existing = await news_repo.get_by_content_hash(session, content_hash)
    return existing is not None


async def is_duplicate(session: AsyncSession, source_url: str, content: str) -> bool:
    """Check both URL and content hash for duplicates."""
    if await is_duplicate_url(session, source_url):
        return True
    if await is_duplicate_content(session, content):
        return True
    return False
