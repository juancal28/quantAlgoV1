"""Tests for GET /pnl/daily endpoint."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db
from apps.api.main import app
from core.storage.models import PnlSnapshot


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
async def test_daily_pnl_empty(client: AsyncClient):
    resp = await client.get("/pnl/daily?strategy=test_strat")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_daily_pnl_returns_snapshot(
    client: AsyncClient, db_session: AsyncSession
):
    snapshot = PnlSnapshot(
        strategy_name="test_strat",
        snapshot_date=date(2025, 6, 15),
        realized_pnl=100.0,
        unrealized_pnl=50.0,
        gross_exposure=0.8,
        peak_pnl=120.0,
        positions={"SPY": {"quantity": 10}},
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(snapshot)
    await db_session.flush()

    resp = await client.get("/pnl/daily?strategy=test_strat")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["realized_pnl"] == 100.0
    assert data[0]["positions"] == {"SPY": {"quantity": 10}}
