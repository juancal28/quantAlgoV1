"""Tests for paper_trade_tick market hours behavior."""

from __future__ import annotations

import logging

import pytest

from apps.mcp_server.schemas import PaperTradeTickInput
from apps.mcp_server.tools.execution import _reset_brokers, paper_trade_tick


@pytest.fixture(autouse=True)
def _cleanup_brokers():
    """Reset broker cache between tests."""
    _reset_brokers()
    yield
    _reset_brokers()


@pytest.mark.asyncio
class TestMarketHoursBehavior:
    """Tests for paper_trade_tick market hours checks."""

    async def test_returns_market_closed_when_outside_hours(
        self, db_session, monkeypatch, mock_settings
    ):
        """paper_trade_tick returns market_open=False when market is closed."""
        mock_settings("TRADING_MODE", "paper")
        mock_settings("PAPER_GUARD", "true")

        monkeypatch.setattr(
            "apps.mcp_server.tools.execution.is_market_open", lambda: False
        )

        params = PaperTradeTickInput(strategy_name="test_strat")
        result = await paper_trade_tick(db_session, params)

        assert result.market_open is False
        assert result.orders == []
        assert result.positions == []
        assert result.pnl_snapshot is None

    async def test_returns_market_open_when_during_hours(
        self, db_session, monkeypatch, mock_settings
    ):
        """paper_trade_tick returns market_open=True when market is open."""
        mock_settings("TRADING_MODE", "paper")
        mock_settings("PAPER_GUARD", "true")

        monkeypatch.setattr(
            "apps.mcp_server.tools.execution.is_market_open", lambda: True
        )

        params = PaperTradeTickInput(strategy_name="nonexistent")
        result = await paper_trade_tick(db_session, params)

        # No active strategy found, but market_open should be True
        assert result.market_open is True

    async def test_logs_warning_outside_market_hours(
        self, db_session, monkeypatch, mock_settings, caplog
    ):
        """paper_trade_tick logs a warning when called outside market hours."""
        mock_settings("TRADING_MODE", "paper")
        mock_settings("PAPER_GUARD", "true")

        monkeypatch.setattr(
            "apps.mcp_server.tools.execution.is_market_open", lambda: False
        )

        params = PaperTradeTickInput(strategy_name="warn_test")

        with caplog.at_level(logging.WARNING):
            await paper_trade_tick(db_session, params)

        assert any("outside market hours" in r.message for r in caplog.records)
