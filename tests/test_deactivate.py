"""Tests for deactivate_strategy() in core.agent.approval and the API endpoint."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from core.agent.approval import deactivate_strategy, submit_for_approval, approve_strategy
from core.storage.models import StrategyAuditLog, StrategyVersion


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


@pytest.mark.asyncio
async def test_deactivate_archives_active_version(db_session, sample_definition):
    """deactivate_strategy() sets status='archived' on the active version."""
    v1 = await submit_for_approval(
        db_session, "test_strat", sample_definition, reason="proposal"
    )
    await approve_strategy(db_session, "test_strat", str(v1.id))

    archived = await deactivate_strategy(db_session, "test_strat")
    assert archived.status == "archived"
    assert archived.name == "test_strat"


@pytest.mark.asyncio
async def test_deactivate_writes_audit_log(db_session, sample_definition):
    """deactivate_strategy() writes an audit log with action='deactivated'."""
    v1 = await submit_for_approval(
        db_session, "test_strat", sample_definition, reason="proposal"
    )
    await approve_strategy(db_session, "test_strat", str(v1.id))

    await deactivate_strategy(
        db_session, "test_strat", reason="manual deactivation", trigger="human"
    )

    stmt = select(StrategyAuditLog).where(
        StrategyAuditLog.strategy_name == "test_strat",
        StrategyAuditLog.action == "deactivated",
    )
    result = await db_session.execute(stmt)
    audits = list(result.scalars().all())
    assert len(audits) == 1
    assert audits[0].trigger == "human"
    assert audits[0].before_definition == sample_definition


@pytest.mark.asyncio
async def test_deactivate_raises_when_no_active_version(db_session):
    """deactivate_strategy() raises ValueError when no active version exists."""
    with pytest.raises(ValueError, match="No active version found"):
        await deactivate_strategy(db_session, "nonexistent_strat")


@pytest.mark.asyncio
async def test_deactivate_scheduler_trigger(db_session, sample_definition):
    """deactivate_strategy() records trigger='scheduler' when called by expiry task."""
    v1 = await submit_for_approval(
        db_session, "test_strat", sample_definition, reason="proposal"
    )
    await approve_strategy(db_session, "test_strat", str(v1.id))

    await deactivate_strategy(
        db_session, "test_strat", reason="TTL expired", trigger="scheduler"
    )

    stmt = select(StrategyAuditLog).where(
        StrategyAuditLog.strategy_name == "test_strat",
        StrategyAuditLog.action == "deactivated",
    )
    result = await db_session.execute(stmt)
    audits = list(result.scalars().all())
    assert len(audits) == 1
    assert audits[0].trigger == "scheduler"


# --- API endpoint tests ---


@pytest.mark.asyncio
async def test_api_deactivate_success(db_session, sample_definition):
    """POST /strategies/{name}/deactivate returns 200 on success."""
    from httpx import ASGITransport, AsyncClient
    from apps.api.main import app
    from apps.api.deps import get_db

    # Setup: create and approve a strategy
    v1 = await submit_for_approval(
        db_session, "test_strat", sample_definition, reason="proposal"
    )
    await approve_strategy(db_session, "test_strat", str(v1.id))

    app.dependency_overrides[get_db] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/strategies/test_strat/deactivate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "archived"
        assert data["name"] == "test_strat"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_deactivate_404_no_active(db_session):
    """POST /strategies/{name}/deactivate returns 404 when no active version."""
    from httpx import ASGITransport, AsyncClient
    from apps.api.main import app
    from apps.api.deps import get_db

    app.dependency_overrides[get_db] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/strategies/nonexistent/deactivate")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
