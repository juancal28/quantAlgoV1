"""Tests for monitoring MCP tools."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from apps.mcp_server.schemas import (
    PnlSummaryInput,
    RecentNewsInput,
    RecentRunsInput,
    StrategyOverviewInput,
    SystemHealthInput,
)
from apps.mcp_server.tools.monitoring import (
    get_pnl_summary,
    get_recent_news_summary,
    get_recent_runs,
    get_strategy_overview,
    get_system_health,
)
from core.storage.models import (
    NewsDocument,
    PnlSnapshot,
    Run,
    StrategyVersion,
)


# ---------- Empty DB tests ----------


@pytest.mark.asyncio
async def test_strategy_overview_empty(db_session):
    result = await get_strategy_overview(
        db_session, StrategyOverviewInput()
    )
    assert result.strategies == []


@pytest.mark.asyncio
async def test_recent_runs_empty(db_session):
    result = await get_recent_runs(db_session, RecentRunsInput())
    assert result.runs == []


@pytest.mark.asyncio
async def test_pnl_summary_empty(db_session):
    result = await get_pnl_summary(
        db_session, PnlSummaryInput(strategy_name="nonexistent")
    )
    assert result.snapshots == []


@pytest.mark.asyncio
async def test_recent_news_empty(db_session):
    result = await get_recent_news_summary(
        db_session, RecentNewsInput()
    )
    assert result.articles == []


# ---------- Seeded data tests ----------


@pytest.mark.asyncio
async def test_strategy_overview_with_data(db_session):
    sv = StrategyVersion(
        id=uuid.uuid4(),
        name="test_strat",
        version=1,
        status="active",
        definition={"name": "test_strat"},
        created_at=datetime.now(timezone.utc),
        reason="test",
        backtest_metrics={"sharpe": 1.2},
    )
    db_session.add(sv)
    await db_session.flush()

    result = await get_strategy_overview(
        db_session, StrategyOverviewInput()
    )
    assert len(result.strategies) == 1
    assert result.strategies[0].name == "test_strat"
    assert result.strategies[0].status == "active"
    assert result.strategies[0].backtest_metrics == {"sharpe": 1.2}


@pytest.mark.asyncio
async def test_strategy_overview_filters_by_status(db_session):
    for status in ("active", "pending_approval", "archived"):
        db_session.add(StrategyVersion(
            id=uuid.uuid4(),
            name=f"strat_{status}",
            version=1,
            status=status,
            definition={},
            created_at=datetime.now(timezone.utc),
            reason="test",
        ))
    await db_session.flush()

    result = await get_strategy_overview(
        db_session, StrategyOverviewInput(status="active")
    )
    assert len(result.strategies) == 1
    assert result.strategies[0].status == "active"


@pytest.mark.asyncio
async def test_recent_runs_with_data(db_session):
    run = Run(
        id=uuid.uuid4(),
        run_type="ingest",
        status="ok",
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        details={"ingested": 5},
    )
    db_session.add(run)
    await db_session.flush()

    result = await get_recent_runs(db_session, RecentRunsInput())
    assert len(result.runs) == 1
    assert result.runs[0].run_type == "ingest"
    assert result.runs[0].status == "ok"


@pytest.mark.asyncio
async def test_system_health_structure(db_session):
    with patch("core.timeutils.is_market_open", return_value=False), \
         patch("core.kb.vectorstore.QdrantVectorStore") as mock_qdrant:
        mock_client = AsyncMock()
        mock_client.get_collections = AsyncMock()
        mock_qdrant.return_value._client = mock_client

        result = await get_system_health(db_session, SystemHealthInput())

    assert result.trading_mode == "paper"
    assert result.paper_guard is True
    assert result.market_open is False
    assert result.last_ingest_run is None
    assert result.news_count_last_2h == 0
    assert isinstance(result.strategy_counts, dict)
    assert "postgres" in result.services
