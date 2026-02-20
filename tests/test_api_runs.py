"""Tests for /runs endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db
from apps.api.main import app
from core.storage.models import Run


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
async def test_recent_runs_empty(client: AsyncClient):
    resp = await client.get("/runs/recent")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_recent_runs_returns_data(
    client: AsyncClient, db_session: AsyncSession
):
    run = Run(
        run_type="ingest",
        status="ok",
        started_at=datetime.now(timezone.utc),
        details={"ingested": 5},
    )
    db_session.add(run)
    await db_session.flush()

    resp = await client.get("/runs/recent")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["run_type"] == "ingest"
    assert data[0]["status"] == "ok"


@pytest.mark.asyncio
async def test_trigger_news_cycle_creates_run(
    client: AsyncClient, db_session: AsyncSession
):
    """POST /runs/news_cycle should create a run record.

    Celery won't be available in tests, so status will be 'failed',
    but the run record should still be created.
    """
    resp = await client.post("/runs/news_cycle")
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert data["status"] in ("dispatched", "failed")
