"""Tests for the auto-approve scheduled task."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent.approval import submit_for_approval
from core.storage.models import StrategyVersion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_DEFINITION = {
    "name": "sentiment_momentum_v1",
    "universe": ["SPY"],
    "signals": [
        {"type": "news_sentiment", "lookback_minutes": 240, "threshold": 0.65, "direction": "long"}
    ],
    "rules": {
        "rebalance_minutes": 60,
        "max_positions": 5,
        "position_sizing": {"type": "equal_weight", "max_position_pct": 0.10},
        "exits": [{"type": "time_stop", "minutes": 360}],
    },
}


async def _create_pending_version(
    session: AsyncSession,
    strategy_name: str = "sentiment_momentum_v1",
    minutes_ago: int = 10,
) -> StrategyVersion:
    """Create a pending_approval strategy version with a backdated created_at."""
    version = await submit_for_approval(
        session,
        strategy_name=strategy_name,
        definition=VALID_DEFINITION,
        reason="test proposal",
        backtest_metrics={"sharpe": 1.0},
    )
    # Backdate created_at so it's older than the threshold
    version.created_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    await session.flush()
    return version


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_approve_disabled_when_zero(mock_settings):
    """When PENDING_APPROVAL_AUTO_APPROVE_MINUTES=0, task returns skipped."""
    from unittest.mock import patch

    mock_settings("PENDING_APPROVAL_AUTO_APPROVE_MINUTES", "0")

    from apps.scheduler.jobs import run_auto_approve

    with patch("apps.scheduler.jobs._is_scheduler_paused", return_value=False), \
         patch("apps.scheduler.jobs._is_autonomous_mode", return_value=False):
        result = run_auto_approve()
    assert result["skipped"] is True
    assert result["reason"] == "auto_approve_disabled"


@pytest.mark.asyncio
async def test_auto_approve_approves_old_versions(db_session: AsyncSession, mock_settings):
    """Versions older than the threshold get auto-approved."""
    mock_settings("PENDING_APPROVAL_AUTO_APPROVE_MINUTES", "5")

    from apps.scheduler.jobs import _run_auto_approve_async

    # Create a version that is 10 minutes old (> 5 min threshold)
    version = await _create_pending_version(db_session, minutes_ago=10)

    result = await _run_auto_approve_async(_session=db_session)

    assert len(result["approved"]) == 1
    assert "sentiment_momentum_v1" in result["approved"][0]
    assert len(result["errors"]) == 0

    # Verify the version status changed
    await db_session.refresh(version)
    assert version.status == "active"
    assert version.approved_by == "auto"


@pytest.mark.asyncio
async def test_auto_approve_skips_recent_versions(db_session: AsyncSession, mock_settings):
    """Versions newer than the threshold are not auto-approved."""
    mock_settings("PENDING_APPROVAL_AUTO_APPROVE_MINUTES", "5")

    from apps.scheduler.jobs import _run_auto_approve_async

    # Create a version that is only 2 minutes old (< 5 min threshold)
    version = await _create_pending_version(db_session, minutes_ago=2)

    result = await _run_auto_approve_async(_session=db_session)

    assert len(result["approved"]) == 0
    assert len(result["errors"]) == 0

    # Verify version remains pending
    await db_session.refresh(version)
    assert version.status == "pending_approval"


@pytest.mark.asyncio
async def test_auto_approve_respects_daily_limit(db_session: AsyncSession, mock_settings):
    """Auto-approve respects STRATEGY_MAX_ACTIVATIONS_PER_DAY."""
    mock_settings("PENDING_APPROVAL_AUTO_APPROVE_MINUTES", "5")
    mock_settings("STRATEGY_MAX_ACTIVATIONS_PER_DAY", "1")

    from apps.scheduler.jobs import _run_auto_approve_async

    # Create two old pending versions for the same strategy
    v1 = await _create_pending_version(db_session, minutes_ago=10)
    v2 = await _create_pending_version(db_session, minutes_ago=10)

    result = await _run_auto_approve_async(_session=db_session)

    # First should succeed, second should hit the daily limit
    assert len(result["approved"]) == 1
    assert len(result["errors"]) == 1
    assert "activation limit" in result["errors"][0].lower() or "Daily activation limit" in result["errors"][0]


@pytest.mark.asyncio
async def test_auto_approve_handles_multiple_strategies(db_session: AsyncSession, mock_settings):
    """Auto-approve works across different strategy names."""
    mock_settings("PENDING_APPROVAL_AUTO_APPROVE_MINUTES", "5")

    from apps.scheduler.jobs import _run_auto_approve_async

    v1 = await _create_pending_version(db_session, strategy_name="sentiment_momentum_v1", minutes_ago=10)
    v2 = await _create_pending_version(db_session, strategy_name="event_risk_off_v1", minutes_ago=10)

    result = await _run_auto_approve_async(_session=db_session)

    assert len(result["approved"]) == 2
    assert len(result["errors"]) == 0
