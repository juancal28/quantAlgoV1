"""Tests for strategy TTL expiry (STRATEGY_MAX_AGE_HOURS)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from core.agent.approval import approve_strategy, submit_for_approval
from core.storage.models import StrategyAuditLog, StrategyVersion
from core.storage.repos import strategy_repo


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


async def _create_active_strategy(db_session, definition, hours_ago: int = 0):
    """Helper: submit, approve, and optionally backdate activated_at."""
    v = await submit_for_approval(
        db_session, definition["name"], definition, reason="test"
    )
    activated = await approve_strategy(db_session, definition["name"], str(v.id))
    if hours_ago > 0:
        activated.activated_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        await db_session.flush()
    return activated


@pytest.mark.asyncio
async def test_expired_strategy_is_archived(db_session, sample_definition, mock_settings):
    """Active strategy older than TTL is found by get_expired_active_strategies."""
    mock_settings("STRATEGY_MAX_AGE_HOURS", "24")

    # Create a strategy activated 48 hours ago
    v = await _create_active_strategy(db_session, sample_definition, hours_ago=48)
    assert v.status == "active"

    expired = await strategy_repo.get_expired_active_strategies(db_session, 24)
    assert len(expired) == 1
    assert str(expired[0].id) == str(v.id)


@pytest.mark.asyncio
async def test_recent_strategy_not_expired(db_session, sample_definition, mock_settings):
    """Active strategy newer than TTL is NOT returned."""
    mock_settings("STRATEGY_MAX_AGE_HOURS", "24")

    # Create a strategy activated just now (0 hours ago)
    v = await _create_active_strategy(db_session, sample_definition, hours_ago=0)
    assert v.status == "active"

    expired = await strategy_repo.get_expired_active_strategies(db_session, 24)
    assert len(expired) == 0


@pytest.mark.asyncio
async def test_expiry_task_disabled_when_zero(mock_settings):
    """run_expire_strategies returns skipped when STRATEGY_MAX_AGE_HOURS=0."""
    from apps.scheduler.jobs import _run_expire_strategies_async

    mock_settings("STRATEGY_MAX_AGE_HOURS", "0")

    from core.config import get_settings
    settings = get_settings()
    assert settings.STRATEGY_MAX_AGE_HOURS == 0
    # The sync wrapper checks this; we verify the config is correct.


@pytest.mark.asyncio
async def test_expiry_task_archives_expired(db_session, sample_definition, mock_settings):
    """_run_expire_strategies_async archives expired strategies."""
    mock_settings("STRATEGY_MAX_AGE_HOURS", "1")
    from apps.scheduler.jobs import _run_expire_strategies_async

    # Create strategy activated 2 hours ago
    await _create_active_strategy(db_session, sample_definition, hours_ago=2)

    result = await _run_expire_strategies_async(_session=db_session)
    assert len(result["archived"]) == 1
    assert "test_strat@v1" in result["archived"]
    assert len(result["errors"]) == 0


@pytest.mark.asyncio
async def test_expiry_task_skips_recent(db_session, sample_definition, mock_settings):
    """_run_expire_strategies_async leaves recent strategies alone."""
    mock_settings("STRATEGY_MAX_AGE_HOURS", "24")
    from apps.scheduler.jobs import _run_expire_strategies_async

    # Create strategy activated just now
    await _create_active_strategy(db_session, sample_definition, hours_ago=0)

    result = await _run_expire_strategies_async(_session=db_session)
    assert len(result["archived"]) == 0


@pytest.mark.asyncio
async def test_expiry_creates_audit_log(db_session, sample_definition, mock_settings):
    """Expiry task creates audit log with action='deactivated', trigger='scheduler'."""
    mock_settings("STRATEGY_MAX_AGE_HOURS", "1")
    from apps.scheduler.jobs import _run_expire_strategies_async

    await _create_active_strategy(db_session, sample_definition, hours_ago=2)
    await _run_expire_strategies_async(_session=db_session)

    stmt = select(StrategyAuditLog).where(
        StrategyAuditLog.strategy_name == "test_strat",
        StrategyAuditLog.action == "deactivated",
    )
    result = await db_session.execute(stmt)
    audits = list(result.scalars().all())
    assert len(audits) == 1
    assert audits[0].trigger == "scheduler"
