"""Paper trade execution MCP tool."""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from apps.mcp_server.schemas import (
    PaperTradeOrderItem,
    PaperTradePnlItem,
    PaperTradePositionItem,
    PaperTradeTickInput,
    PaperTradeTickOutput,
)
from core.execution.alpaca_paper import get_broker
from core.execution.broker_base import BrokerBase
from core.execution.price_feed import get_price_feed
from core.execution.risk import DailyLossCircuitBreaker
from core.execution.signal_evaluator import execute_signals, generate_signals_from_definition
from core.logging import get_logger
from core.timeutils import is_market_open

logger = get_logger(__name__)

# Module-level broker cache: one broker per strategy
_brokers: dict[str, BrokerBase] = {}

# Rebalance throttle: track last signal evaluation timestamp per strategy
_last_evaluation: dict[str, float] = {}


def _reset_brokers() -> None:
    """Clear broker cache. For test cleanup only."""
    _brokers.clear()
    _last_evaluation.clear()


async def paper_trade_tick(
    session: AsyncSession, params: PaperTradeTickInput
) -> PaperTradeTickOutput:
    """Execute a single paper trading tick for a strategy.

    1. Check market hours — no-op if closed
    2. Load active strategy definition from DB
    3. Get/create broker
    4. Rehydrate circuit breaker from DB
    5. Fetch current prices via price_feed
    6. Evaluate signals (throttled by rebalance_minutes)
    7. Pre-check circuit breaker
    8. Execute orders via execute_signals (SELLs then BUYs)
    9. Recompute PnL with real current prices
    10. Persist PnL snapshot
    11. Return positions/orders/pnl state
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

    # 2. Load active strategy definition from DB
    active = await strategy_repo.get_active_by_name(session, params.strategy_name)
    if active is None:
        logger.warning(
            "No active strategy found for name=%s", params.strategy_name
        )
        return PaperTradeTickOutput(
            orders=[], positions=[], pnl_snapshot=None, market_open=True
        )

    definition = active.definition

    # 3. Get or create broker
    if params.strategy_name not in _brokers:
        _brokers[params.strategy_name] = get_broker()
    broker = _brokers[params.strategy_name]

    # 4. Rehydrate circuit breaker from DB
    breaker = DailyLossCircuitBreaker(params.strategy_name)
    existing_snapshot = await breaker.rehydrate(session)

    # 5. Fetch current prices via price_feed
    universe = definition.get("universe", [])
    price_feed = get_price_feed(session)
    current_prices = price_feed.get_prices(universe)

    # Fill in entry prices for any held positions not in price feed
    for pos in broker.get_positions():
        if pos.ticker not in current_prices:
            current_prices[pos.ticker] = pos.avg_entry_price

    # 6. Evaluate signals (throttled by rebalance_minutes)
    tick_orders = []
    rebalance_minutes = definition.get("rules", {}).get("rebalance_minutes", 60)
    now = time.monotonic()
    last_eval = _last_evaluation.get(params.strategy_name, 0.0)
    elapsed_minutes = (now - last_eval) / 60.0

    should_evaluate = last_eval == 0.0 or elapsed_minutes >= rebalance_minutes
    if should_evaluate:
        signals = await generate_signals_from_definition(
            session, definition, current_prices
        )

        # 7. Pre-check circuit breaker before placing orders
        realized = broker.realized_pnl
        unrealized = broker.unrealized_pnl(current_prices)
        exposure = broker.gross_exposure(current_prices)
        peak = existing_snapshot.peak_pnl if existing_snapshot else 0.0
        if (realized + unrealized) > peak:
            peak = realized + unrealized

        tripped, _ = breaker.check(
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            gross_exposure=exposure,
            peak_pnl=peak,
            positions=None,
        )

        # 8. Execute orders
        tick_orders = execute_signals(
            broker=broker,
            signals=signals,
            current_prices=current_prices,
            definition=definition,
            circuit_breaker_tripped=tripped,
        )

        _last_evaluation[params.strategy_name] = now

        if tripped:
            logger.warning(
                "Circuit breaker tripped for strategy=%s, skipping order generation",
                params.strategy_name,
            )

    # 9. Recompute PnL with real current prices
    realized = broker.realized_pnl
    unrealized = broker.unrealized_pnl(current_prices)
    exposure = broker.gross_exposure(current_prices)
    peak = existing_snapshot.peak_pnl if existing_snapshot else 0.0
    if (realized + unrealized) > peak:
        peak = realized + unrealized

    # 10. Check circuit breaker and persist snapshot
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

    await pnl_repo.save_snapshot(session, snapshot)
    await session.commit()

    # 11. Build response
    order_items = [
        PaperTradeOrderItem(
            order_id=o.order_id,
            ticker=o.ticker,
            side=o.side,
            quantity=o.quantity,
            price=o.price,
            status=o.status,
        )
        for o in tick_orders
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
