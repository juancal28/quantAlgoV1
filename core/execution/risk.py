"""Risk management."""

from __future__ import annotations

from datetime import date, timezone, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.storage.models import PnlSnapshot


class DailyLossCircuitBreaker:
    """Circuit breaker that trips when daily loss exceeds the configured limit.

    State is persisted to Postgres via pnl_snapshots — never held only in memory.
    """

    def __init__(self, strategy_name: str):
        self.strategy_name = strategy_name

    def check(
        self,
        realized_pnl: float,
        unrealized_pnl: float,
        gross_exposure: float,
        peak_pnl: float,
        positions: dict | None,
    ) -> tuple[bool, PnlSnapshot]:
        """Check if the daily loss limit has been breached.

        Returns (tripped, snapshot). The caller is responsible for persisting
        the snapshot to the database.
        """
        from core.config import get_settings

        s = get_settings()
        total_pnl = realized_pnl + unrealized_pnl

        # Update peak
        if total_pnl > peak_pnl:
            peak_pnl = total_pnl

        # Check if loss exceeds threshold
        # Loss is measured as negative PnL relative to initial cash
        loss_pct = -total_pnl / s.PAPER_INITIAL_CASH if s.PAPER_INITIAL_CASH > 0 else 0.0
        tripped = loss_pct >= s.RISK_MAX_DAILY_LOSS_PCT

        snapshot = PnlSnapshot(
            strategy_name=self.strategy_name,
            snapshot_date=date.today(),
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            gross_exposure=gross_exposure,
            peak_pnl=peak_pnl,
            positions=positions or {},
            created_at=datetime.now(timezone.utc),
        )

        return tripped, snapshot

    async def rehydrate(
        self, session: AsyncSession, strategy_name: str | None = None
    ) -> PnlSnapshot | None:
        """Load today's PnL snapshot from the database.

        Used on startup or after restart to restore circuit breaker state.
        """
        from core.storage.repos import pnl_repo

        name = strategy_name or self.strategy_name
        return await pnl_repo.get_snapshot(session, name, date.today())


def check_exposure_limit(gross_exposure: float, portfolio_value: float) -> bool:
    """Return True if gross exposure is within the allowed limit."""
    from core.config import get_settings

    if portfolio_value <= 0:
        return gross_exposure <= 0
    ratio = gross_exposure / portfolio_value
    return ratio <= get_settings().RISK_MAX_GROSS_EXPOSURE


def check_trade_rate_limit(recent_order_count: int) -> bool:
    """Return True if recent order count is within the allowed rate limit."""
    from core.config import get_settings

    return recent_order_count < get_settings().RISK_MAX_TRADES_PER_HOUR
