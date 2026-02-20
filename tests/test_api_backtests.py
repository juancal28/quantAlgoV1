"""Tests for POST /strategies/{name}/backtest endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db
from apps.api.main import app
from apps.mcp_server.schemas import BacktestMetricsOutput, RunBacktestOutput
from core.storage.models import StrategyVersion


@pytest.fixture
async def client(db_session: AsyncSession):
    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


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
async def test_backtest_404_no_active_strategy(client: AsyncClient):
    resp = await client.post(
        "/strategies/nonexistent/backtest",
        json={"start": "2024-01-01", "end": "2025-01-01"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_backtest_200_with_mock(
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

    mock_output = RunBacktestOutput(
        metrics=BacktestMetricsOutput(
            cagr=0.12,
            sharpe=1.5,
            max_drawdown=0.10,
            win_rate=0.55,
            turnover=2.0,
            avg_trade_return=0.005,
        ),
        passed=True,
    )

    with patch(
        "apps.mcp_server.tools.backtest.run_backtest_tool",
        new_callable=AsyncMock,
        return_value=mock_output,
    ):
        resp = await client.post(
            "/strategies/test_strat/backtest",
            json={"start": "2024-01-01", "end": "2025-01-01"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is True
    assert data["metrics"]["sharpe"] == 1.5
