"""Tests for FastAPI strategy endpoints and health check."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db
from apps.api.main import app
from core.agent.approval import submit_for_approval
from core.storage.models import StrategyVersion


@pytest.fixture
def sample_definition() -> dict:
    return {
        "name": "test_strat",
        "universe": ["SPY", "QQQ"],
        "signals": [{"type": "news_sentiment", "threshold": 0.5}],
        "rules": {
            "rebalance_minutes": 60,
            "max_positions": 5,
            "position_sizing": {"type": "equal_weight", "max_position_pct": 0.10},
            "exits": [{"type": "time_stop", "minutes": 360}],
        },
    }


@pytest.fixture
async def client(db_session: AsyncSession):
    """Create an httpx async test client with DB dependency overridden."""

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["trading_mode"] == "paper"


@pytest.mark.asyncio
async def test_list_strategies_empty(client: AsyncClient):
    resp = await client.get("/strategies")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_strategies_with_data(
    client: AsyncClient, db_session: AsyncSession, sample_definition
):
    v = StrategyVersion(
        name="test_strat",
        version=1,
        status="pending_approval",
        definition=sample_definition,
        reason="test",
    )
    db_session.add(v)
    await db_session.flush()

    resp = await client.get("/strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "test_strat"


@pytest.mark.asyncio
async def test_get_active_404_when_missing(client: AsyncClient):
    resp = await client.get("/strategies/nonexistent/active")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_active_200_when_found(
    client: AsyncClient, db_session: AsyncSession, sample_definition
):
    v = StrategyVersion(
        name="test_strat",
        version=1,
        status="active",
        definition=sample_definition,
        reason="test",
    )
    db_session.add(v)
    await db_session.flush()

    resp = await client.get("/strategies/test_strat/active")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_list_versions_404_when_missing(client: AsyncClient):
    resp = await client.get("/strategies/nonexistent/versions")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_versions_200_when_found(
    client: AsyncClient, db_session: AsyncSession, sample_definition
):
    v = StrategyVersion(
        name="test_strat",
        version=1,
        status="pending_approval",
        definition=sample_definition,
        reason="test",
    )
    db_session.add(v)
    await db_session.flush()

    resp = await client.get("/strategies/test_strat/versions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


@pytest.mark.asyncio
async def test_approve_200_on_success(
    client: AsyncClient, db_session: AsyncSession, sample_definition
):
    version = await submit_for_approval(
        db_session, "test_strat", sample_definition, reason="proposal"
    )
    resp = await client.post(
        f"/strategies/test_strat/approve/{version.id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["approved_by"] == "human"


@pytest.mark.asyncio
async def test_approve_400_wrong_status(
    client: AsyncClient, db_session: AsyncSession, sample_definition
):
    v = StrategyVersion(
        name="test_strat",
        version=1,
        status="active",
        definition=sample_definition,
        reason="already active",
    )
    db_session.add(v)
    await db_session.flush()

    resp = await client.post(f"/strategies/test_strat/approve/{v.id}")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_approve_400_nonexistent(client: AsyncClient):
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(f"/strategies/test_strat/approve/{fake_id}")
    assert resp.status_code == 400
