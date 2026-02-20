"""Async database engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import get_settings

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=(settings.APP_ENV == "dev"),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_recycle=300,
        )
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async generator that yields a session and closes it when done.

    Use as a FastAPI dependency or async context manager.
    """
    factory = _get_session_factory()
    async with factory() as session:
        yield session


def reset_engine() -> None:
    """Reset engine and session factory. For tests only."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
