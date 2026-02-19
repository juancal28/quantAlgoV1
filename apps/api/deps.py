"""FastAPI dependency injection."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from core.storage.db import get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session. Use as a FastAPI Depends()."""
    async for session in get_session():
        yield session
