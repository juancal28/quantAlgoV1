"""Tests for GET /news/recent endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db
from apps.api.main import app
from core.storage.models import NewsDocument


@pytest.fixture
async def client(db_session: AsyncSession):
    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_recent_news_empty(client: AsyncClient):
    resp = await client.get("/news/recent")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_recent_news_returns_article(
    client: AsyncClient, db_session: AsyncSession
):
    now = datetime.now(timezone.utc)
    doc = NewsDocument(
        id=uuid.uuid4(),
        source="rss",
        source_url="https://example.com/article1",
        title="Test Article",
        published_at=now,
        fetched_at=now,
        content="Some financial news about AAPL and MSFT",
        content_hash="abc123",
        metadata_={"tickers": ["AAPL", "MSFT"]},
    )
    db_session.add(doc)
    await db_session.flush()

    resp = await client.get("/news/recent?minutes=60")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Test Article"
    assert data[0]["tickers"] == ["AAPL", "MSFT"]


@pytest.mark.asyncio
async def test_recent_news_respects_limit(
    client: AsyncClient, db_session: AsyncSession
):
    now = datetime.now(timezone.utc)
    for i in range(5):
        doc = NewsDocument(
            id=uuid.uuid4(),
            source="rss",
            source_url=f"https://example.com/article{i}",
            title=f"Article {i}",
            published_at=now,
            fetched_at=now,
            content=f"Content {i}",
            content_hash=f"hash{i}",
        )
        db_session.add(doc)
    await db_session.flush()

    resp = await client.get("/news/recent?minutes=60&limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
