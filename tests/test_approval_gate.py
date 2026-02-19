"""Tests for core.agent.approval — approval gate logic."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from core.agent.approval import submit_for_approval
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
async def test_creates_pending_approval_version(db_session, sample_definition):
    version = await submit_for_approval(
        db_session, "test_strat", sample_definition, reason="test proposal"
    )
    assert version.status == "pending_approval"
    assert version.name == "test_strat"
    assert version.version == 1


@pytest.mark.asyncio
async def test_status_is_never_active(db_session, sample_definition):
    version = await submit_for_approval(
        db_session, "test_strat", sample_definition, reason="test proposal"
    )
    assert version.status != "active"
    assert version.activated_at is None
    assert version.approved_by is None


@pytest.mark.asyncio
async def test_writes_audit_log(db_session, sample_definition):
    version = await submit_for_approval(
        db_session, "test_strat", sample_definition, reason="test proposal"
    )
    # Query all audit logs for this strategy
    stmt = select(StrategyAuditLog).where(
        StrategyAuditLog.strategy_name == "test_strat"
    )
    result = await db_session.execute(stmt)
    audits = list(result.scalars().all())
    assert len(audits) == 1
    audit = audits[0]
    assert audit.action == "proposed"
    assert audit.trigger == "agent"
    assert audit.after_definition == sample_definition


@pytest.mark.asyncio
async def test_increments_version_number(db_session, sample_definition):
    v1 = await submit_for_approval(
        db_session, "test_strat", sample_definition, reason="first"
    )
    assert v1.version == 1

    v2 = await submit_for_approval(
        db_session, "test_strat", sample_definition, reason="second"
    )
    assert v2.version == 2


@pytest.mark.asyncio
async def test_records_before_definition_when_active_exists(db_session, sample_definition):
    # Create an active version manually
    active_def = {"name": "test_strat", "universe": ["SPY"]}
    active = StrategyVersion(
        name="test_strat",
        version=1,
        status="active",
        definition=active_def,
        reason="initial",
    )
    db_session.add(active)
    await db_session.flush()

    # Submit new proposal
    v2 = await submit_for_approval(
        db_session, "test_strat", sample_definition, reason="update"
    )
    assert v2.version == 2

    # Query audit logs for the strategy — find the one for v2
    stmt = (
        select(StrategyAuditLog)
        .where(StrategyAuditLog.strategy_name == "test_strat")
        .order_by(StrategyAuditLog.timestamp.desc())
    )
    result = await db_session.execute(stmt)
    audits = list(result.scalars().all())
    # Should have exactly 1 audit log (the proposal for v2)
    assert len(audits) == 1
    audit = audits[0]
    assert audit.before_definition == active_def
    assert audit.after_definition == sample_definition
