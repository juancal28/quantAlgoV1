"""Tests for risk management circuit breaker with DB persistence."""

from __future__ import annotations

import pytest

from core.execution.risk import (
    DailyLossCircuitBreaker,
    check_exposure_limit,
    check_trade_rate_limit,
)
from core.storage.repos import pnl_repo


@pytest.mark.asyncio
class TestDailyLossCircuitBreaker:
    """Tests for DailyLossCircuitBreaker."""

    async def test_not_tripped_within_limit(self, mock_settings):
        """Breaker does NOT trip when loss is within limit."""
        mock_settings("PAPER_INITIAL_CASH", "100000")
        mock_settings("RISK_MAX_DAILY_LOSS_PCT", "0.02")

        breaker = DailyLossCircuitBreaker("test_strategy")
        tripped, snapshot = breaker.check(
            realized_pnl=-500.0,  # -0.5% loss, under 2% threshold
            unrealized_pnl=0.0,
            gross_exposure=10000.0,
            peak_pnl=0.0,
            positions={},
        )
        assert tripped is False
        assert snapshot.strategy_name == "test_strategy"
        assert snapshot.realized_pnl == -500.0

    async def test_trips_at_daily_loss_limit(self, mock_settings):
        """Breaker trips when loss reaches the daily limit."""
        mock_settings("PAPER_INITIAL_CASH", "100000")
        mock_settings("RISK_MAX_DAILY_LOSS_PCT", "0.02")

        breaker = DailyLossCircuitBreaker("test_strategy")
        tripped, snapshot = breaker.check(
            realized_pnl=-1500.0,
            unrealized_pnl=-600.0,  # Total loss: -2100 = -2.1%, over 2%
            gross_exposure=10000.0,
            peak_pnl=0.0,
            positions={},
        )
        assert tripped is True

    async def test_snapshot_persisted_and_retrieved(self, db_session, mock_settings):
        """PnL snapshot can be persisted and retrieved."""
        mock_settings("PAPER_INITIAL_CASH", "100000")
        mock_settings("RISK_MAX_DAILY_LOSS_PCT", "0.02")

        breaker = DailyLossCircuitBreaker("persist_test")
        _, snapshot = breaker.check(
            realized_pnl=-100.0,
            unrealized_pnl=50.0,
            gross_exposure=5000.0,
            peak_pnl=200.0,
            positions={"SPY": {"quantity": 10}},
        )

        saved = await pnl_repo.save_snapshot(db_session, snapshot)
        await db_session.commit()

        retrieved = await pnl_repo.get_snapshot(
            db_session, "persist_test", snapshot.snapshot_date
        )
        assert retrieved is not None
        assert float(retrieved.realized_pnl) == -100.0
        assert float(retrieved.unrealized_pnl) == 50.0

    async def test_rehydrate_returns_todays_snapshot(self, db_session, mock_settings):
        """rehydrate() returns today's snapshot from the DB."""
        mock_settings("PAPER_INITIAL_CASH", "100000")
        mock_settings("RISK_MAX_DAILY_LOSS_PCT", "0.02")

        breaker = DailyLossCircuitBreaker("rehydrate_test")
        _, snapshot = breaker.check(
            realized_pnl=-300.0,
            unrealized_pnl=0.0,
            gross_exposure=8000.0,
            peak_pnl=100.0,
            positions={},
        )
        await pnl_repo.save_snapshot(db_session, snapshot)
        await db_session.commit()

        result = await breaker.rehydrate(db_session)
        assert result is not None
        assert float(result.realized_pnl) == -300.0

    async def test_rehydrate_returns_none_when_empty(self, db_session, mock_settings):
        """rehydrate() returns None when no snapshot exists."""
        mock_settings("PAPER_INITIAL_CASH", "100000")

        breaker = DailyLossCircuitBreaker("nonexistent")
        result = await breaker.rehydrate(db_session)
        assert result is None

    async def test_breaker_works_after_restart(self, db_session, mock_settings):
        """Breaker state survives a simulated restart (persist -> new instance -> rehydrate)."""
        mock_settings("PAPER_INITIAL_CASH", "100000")
        mock_settings("RISK_MAX_DAILY_LOSS_PCT", "0.02")

        # First instance: create and persist
        breaker1 = DailyLossCircuitBreaker("restart_test")
        _, snapshot = breaker1.check(
            realized_pnl=-1000.0,
            unrealized_pnl=-1200.0,  # Total: -2200 = -2.2% => tripped
            gross_exposure=20000.0,
            peak_pnl=0.0,
            positions={"AAPL": {"quantity": 5}},
        )
        await pnl_repo.save_snapshot(db_session, snapshot)
        await db_session.commit()

        # Second instance: simulate restart by creating a fresh breaker
        breaker2 = DailyLossCircuitBreaker("restart_test")
        rehydrated = await breaker2.rehydrate(db_session)
        assert rehydrated is not None

        # Re-check using rehydrated state
        tripped, _ = breaker2.check(
            realized_pnl=float(rehydrated.realized_pnl),
            unrealized_pnl=float(rehydrated.unrealized_pnl),
            gross_exposure=float(rehydrated.gross_exposure),
            peak_pnl=float(rehydrated.peak_pnl),
            positions=rehydrated.positions,
        )
        assert tripped is True

    async def test_zero_pnl_does_not_trip(self, mock_settings):
        """Zero PnL should not trip the breaker."""
        mock_settings("PAPER_INITIAL_CASH", "100000")
        mock_settings("RISK_MAX_DAILY_LOSS_PCT", "0.02")

        breaker = DailyLossCircuitBreaker("zero_test")
        tripped, _ = breaker.check(
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            gross_exposure=0.0,
            peak_pnl=0.0,
            positions={},
        )
        assert tripped is False


class TestRiskHelpers:
    """Tests for standalone risk helper functions."""

    def test_check_exposure_within_limit(self, mock_settings):
        mock_settings("RISK_MAX_GROSS_EXPOSURE", "1.0")
        assert check_exposure_limit(90000.0, 100000.0) is True

    def test_check_exposure_exceeds_limit(self, mock_settings):
        mock_settings("RISK_MAX_GROSS_EXPOSURE", "1.0")
        assert check_exposure_limit(110000.0, 100000.0) is False

    def test_check_trade_rate_within_limit(self, mock_settings):
        mock_settings("RISK_MAX_TRADES_PER_HOUR", "30")
        assert check_trade_rate_limit(10) is True

    def test_check_trade_rate_exceeds_limit(self, mock_settings):
        mock_settings("RISK_MAX_TRADES_PER_HOUR", "30")
        assert check_trade_rate_limit(30) is False
