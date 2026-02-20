"""Paper trade execution MCP tool."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.mcp_server.schemas import (
    PaperTradeOrderItem,
    PaperTradePnlItem,
    PaperTradePositionItem,
    PaperTradeTickInput,
    PaperTradeTickOutput,
)
from core.execution.paper_broker import PaperBroker
from core.execution.risk import DailyLossCircuitBreaker
from core.logging import get_logger
from core.timeutils import is_market_open

logger = get_logger(__name__)

# Module-level broker cache: one PaperBroker per strategy
_brokers: dict[str, PaperBroker] = {}


def _reset_brokers() -> None:
    """Clear broker cache. For test cleanup only."""
    _brokers.clear()


async def paper_trade_tick(
    session: AsyncSession, params: PaperTradeTickInput
) -> PaperTradeTickOutput:
    """Execute a single paper trading tick for a strategy.

    1. Check market hours — no-op if closed
    2. Load active strategy
    3. Get/create PaperBroker
    4. Rehydrate circuit breaker from DB
    5. Compute PnL state
    6. Check circuit breaker
    7. Persist snapshot
    8. Return positions/orders/pnl state
    """
    from core.storage.repos import pnl_repo, strategy_repo

    # 1. Check market hours
    if not is_market_open():
        logger.warning(
            "paper_trade_tick called outside market hours for strategy=%s",
            params.strategy_name,
        )
        return PaperTradeTickOutput(
            orders=[], positions=[], pnl_snapshot=None, market_open=False
        )

    # 2. Load active strategy
    active = await strategy_repo.get_active_by_name(session, params.strategy_name)
    if active is None:
        logger.warning(
            "No active strategy found for name=%s", params.strategy_name
        )
        return PaperTradeTickOutput(
            orders=[], positions=[], pnl_snapshot=None, market_open=True
        )

    # 3. Get or create PaperBroker
    if params.strategy_name not in _brokers:
        _brokers[params.strategy_name] = PaperBroker()
    broker = _brokers[params.strategy_name]

    # 4. Rehydrate circuit breaker from DB
    breaker = DailyLossCircuitBreaker(params.strategy_name)
    existing_snapshot = await breaker.rehydrate(session)

    # Use current dummy prices (entry prices) for PnL computation
    # In production, this would fetch real-time prices
    current_prices: dict[str, float] = {}
    for pos in broker.get_positions():
        current_prices[pos.ticker] = pos.avg_entry_price

    # 5. Compute PnL state
    realized = broker.realized_pnl
    unrealized = broker.unrealized_pnl(current_prices)
    exposure = broker.gross_exposure(current_prices)
    peak = existing_snapshot.peak_pnl if existing_snapshot else 0.0
    if (realized + unrealized) > peak:
        peak = realized + unrealized

    # 6. Check circuit breaker
    positions_dict = {
        pos.ticker: {"quantity": pos.quantity, "avg_entry_price": pos.avg_entry_price}
        for pos in broker.get_positions()
    }
    tripped, snapshot = breaker.check(
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        gross_exposure=exposure,
        peak_pnl=peak,
        positions=positions_dict,
    )

    if tripped:
        logger.warning(
            "Circuit breaker tripped for strategy=%s, skipping order generation",
            params.strategy_name,
        )

    # 7. Persist snapshot
    await pnl_repo.save_snapshot(session, snapshot)
    await session.commit()

    # 8. Build response
    order_items = [
        PaperTradeOrderItem(
            order_id=o.order_id,
            ticker=o.ticker,
            side=o.side,
            quantity=o.quantity,
            price=o.price,
            status=o.status,
        )
        for o in broker.get_orders()
    ]

    position_items = [
        PaperTradePositionItem(
            ticker=p.ticker,
            quantity=p.quantity,
            avg_entry_price=p.avg_entry_price,
            market_value=p.quantity * current_prices.get(p.ticker, p.avg_entry_price),
            unrealized_pnl=(current_prices.get(p.ticker, p.avg_entry_price) - p.avg_entry_price) * p.quantity,
        )
        for p in broker.get_positions()
    ]

    pnl_item = PaperTradePnlItem(
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        gross_exposure=exposure,
        peak_pnl=peak,
    )

    return PaperTradeTickOutput(
        orders=order_items,
        positions=position_items,
        pnl_snapshot=pnl_item,
        market_open=True,
    )
