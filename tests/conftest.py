"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import os
import uuid as _uuid

# Set test env vars BEFORE any application imports
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("TRADING_MODE", "paper")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "mock")
os.environ.setdefault("SENTIMENT_PROVIDER", "mock")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PAPER_GUARD", "true")

import sqlite3

import pytest
from sqlalchemy import JSON, String, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import _reset_settings, get_settings
from core.storage.models import Base

# Register UUID adapter for sqlite3 so it knows how to bind uuid.UUID objects
sqlite3.register_adapter(_uuid.UUID, lambda u: str(u))
sqlite3.register_converter("UUID", lambda b: _uuid.UUID(b.decode()))


@pytest.fixture(autouse=True)
def _reset_config(monkeypatch):
    """Reset the settings singleton before each test so env changes take effect."""
    _reset_settings()
    yield
    _reset_settings()


@pytest.fixture
def mock_settings(monkeypatch):
    """Helper fixture to override settings via env vars.

    Usage:
        def test_something(mock_settings):
            mock_settings("TRADING_MODE", "paper")
            settings = get_settings()
    """

    def _set(key: str, value: str):
        monkeypatch.setenv(key, value)
        _reset_settings()

    return _set


def _adapt_columns_for_sqlite(base):
    """Remap Postgres-specific types so they work on SQLite.

    JSONB  -> JSON
    UUID   -> String(36)
    """
    from sqlalchemy.dialects.postgresql import JSONB, UUID

    for table in base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()
            elif isinstance(col.type, UUID):
                col.type = String(36)


@pytest.fixture
async def db_session():
    """Async fixture: creates all tables in an in-memory SQLite DB,
    yields a session, then tears down."""
    engine = create_async_engine("sqlite+aiosqlite:///", echo=False)

    _adapt_columns_for_sqlite(Base)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
