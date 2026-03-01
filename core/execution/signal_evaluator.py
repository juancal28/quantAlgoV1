"""Signal evaluation engine for live/paper execution.

Evaluates strategy signals from the definition JSON using real DB data,
then orchestrates order placement through the broker.

Async signal evaluation stays in Python (DB-bound).
Synchronous reconciliation and order orchestration delegate to C++ when
using the PaperBroker.
"""

from __future__ import annotations

import math

from sqlalchemy.ext.asyncio import AsyncSession

from _quant_core import cpp_reconcile_positions, cpp_execute_signals

from core.execution.broker_base import BrokerBase, Order
from core.execution.position_sizing import compute_order_quantity
from core.execution.risk import check_exposure_limit, check_trade_rate_limit
from core.logging import get_logger

logger = get_logger(__name__)


async def evaluate_news_sentiment_signal(
    session: AsyncSession,
    signal_config: dict,
    universe: list[str],
) -> dict[str, float]:
    """Evaluate a news_sentiment signal: query recent news, group sentiment by ticker.

    Returns {ticker: avg_sentiment_score} for tickers that exceed the threshold.
    Only tickers in `universe` are considered.
    """
    from core.storage.repos import news_repo

    lookback_minutes = signal_config.get("lookback_minutes", 240)
    threshold = signal_config.get("threshold", 0.65)

    docs = await news_repo.get_recent(session, minutes=lookback_minutes, limit=500)
    if not docs:
        logger.info("No recent news docs in lookback window of %d minutes", lookback_minutes)
        return {}

    # Group sentiment scores by ticker
    ticker_scores: dict[str, list[float]] = {}
    for doc in docs:
        if doc.sentiment_score is None:
            continue
        tickers_in_doc = []
        if doc.metadata_ and isinstance(doc.metadata_, dict):
            tickers_in_doc = doc.metadata_.get("tickers", [])
        for ticker in tickers_in_doc:
            if ticker in universe:
                ticker_scores.setdefault(ticker, []).append(doc.sentiment_score)

    # Compute per-ticker average and filter by threshold
    result: dict[str, float] = {}
    for ticker, scores in ticker_scores.items():
        avg = sum(scores) / len(scores)
        if avg >= threshold:
            result[ticker] = avg

    return result


async def evaluate_volatility_filter(
    session: AsyncSession,
    signal_config: dict,
) -> bool:
    """Evaluate a volatility_filter signal using VIXY as VIX proxy.

    Returns True if volatility is within acceptable range (signal passes),
    False if risk-off (volatility too high).
    Defaults to True (optimistic) if no VIXY data is available.
    """
    from core.storage.repos import market_data_repo

    max_vix = signal_config.get("max_vix", 25)

    bars = await market_data_repo.get_bars_for_ticker(session, "VIXY", limit=1)
    if not bars:
        logger.info("No VIXY data available; defaulting volatility filter to PASS")
        return True

    # lookahead guard: shift(1) — use open price as proxy
    vixy_price = float(bars[0].open)
    if vixy_price > max_vix:
        logger.info("Volatility filter FAIL: VIXY=%.2f > max_vix=%.1f", vixy_price, max_vix)
        return False

    logger.info("Volatility filter PASS: VIXY=%.2f <= max_vix=%.1f", vixy_price, max_vix)
    return True


async def generate_signals_from_definition(
    session: AsyncSession,
    definition: dict,
    current_prices: dict[str, float],
) -> dict[str, str]:
    """Evaluate all signals in a strategy definition.

    Returns {ticker: direction} where direction is "long" or "flat".
    Processes volatility_filter first as a gate; if it fails, all tickers go flat.
    Then evaluates news_sentiment to determine which tickers get a "long" signal.
    """
    universe = definition.get("universe", [])
    signals_config = definition.get("signals", [])

    # Start with all tickers flat
    result: dict[str, str] = {t: "flat" for t in universe if t in current_prices}

    # Process volatility_filter first (gate)
    for sig in signals_config:
        if sig.get("type") == "volatility_filter":
            vol_pass = await evaluate_volatility_filter(session, sig)
            if not vol_pass:
                logger.info("Volatility filter tripped — all signals flat")
                return result

    # Process news_sentiment signals
    for sig in signals_config:
        if sig.get("type") == "news_sentiment":
            direction = sig.get("direction", "long")
            sentiment_tickers = await evaluate_news_sentiment_signal(
                session, sig, universe
            )
            for ticker in sentiment_tickers:
                if ticker in result:
                    result[ticker] = direction

    return result


def reconcile_positions(
    signals: dict[str, str],
    current_positions: dict[str, float],
) -> tuple[list[str], list[str]]:
    """Compare target signals vs held positions — delegates to C++.

    Returns (tickers_to_buy, tickers_to_sell).
    - tickers_to_buy: tickers with "long" signal not currently held
    - tickers_to_sell: tickers currently held but signal is "flat" or not in signals
    """
    result = cpp_reconcile_positions(signals, current_positions)
    return result.to_buy, result.to_sell


def execute_signals(
    broker: BrokerBase,
    signals: dict[str, str],
    current_prices: dict[str, float],
    definition: dict,
    circuit_breaker_tripped: bool,
) -> list[Order]:
    """Orchestrate order placement based on evaluated signals.

    For PaperBroker (with C++ backend), delegates the full sells-then-buys
    orchestration to C++. For other brokers (e.g. AlpacaPaperBroker),
    keeps the Python orchestration (API-bound).
    """
    from core.execution.paper_broker import PaperBroker

    rules = definition.get("rules", {})
    max_positions = rules.get("max_positions", 5)
    sizing_config = rules.get("position_sizing", {})

    # If using PaperBroker with C++ backend, delegate entirely to C++
    if isinstance(broker, PaperBroker) and hasattr(broker, "_cpp"):
        from core.config import get_settings
        s = get_settings()

        max_pos_pct = s.RISK_MAX_POSITION_PCT
        if sizing_config:
            max_pos_pct = min(
                sizing_config.get("max_position_pct", max_pos_pct),
                max_pos_pct,
            )

        cpp_orders = cpp_execute_signals(
            broker._cpp,
            signals,
            current_prices,
            max_positions,
            max_pos_pct,
            circuit_breaker_tripped,
            s.RISK_MAX_GROSS_EXPOSURE,
            s.RISK_MAX_TRADES_PER_HOUR,
        )

        return [
            Order(
                ticker=o.ticker,
                side=o.side,
                quantity=o.quantity,
                price=o.price,
                status=o.status,
            )
            for o in cpp_orders
        ]

    # Fallback: Python orchestration for non-PaperBroker (e.g. AlpacaPaperBroker)
    return _execute_signals_python(
        broker, signals, current_prices, definition, circuit_breaker_tripped,
    )


def _execute_signals_python(
    broker: BrokerBase,
    signals: dict[str, str],
    current_prices: dict[str, float],
    definition: dict,
    circuit_breaker_tripped: bool,
) -> list[Order]:
    """Python fallback for execute_signals (API-bound brokers)."""
    if circuit_breaker_tripped:
        logger.warning("Circuit breaker tripped — skipping all orders")
        return []

    # Current positions as {ticker: quantity}
    current_positions = {p.ticker: p.quantity for p in broker.get_positions()}

    tickers_to_buy, tickers_to_sell = reconcile_positions(signals, current_positions)

    if not tickers_to_buy and not tickers_to_sell:
        return []

    # Get strategy rules
    rules = definition.get("rules", {})
    max_positions = rules.get("max_positions", 5)
    sizing_config = rules.get("position_sizing", {})

    # Check trade rate limit (count existing orders this session as proxy)
    recent_order_count = len(broker.get_orders())
    if not check_trade_rate_limit(recent_order_count):
        logger.warning("Trade rate limit reached — skipping all orders")
        return []

    orders: list[Order] = []

    # Execute SELLs first to free up cash
    for ticker in tickers_to_sell:
        qty = current_positions.get(ticker, 0)
        if qty <= 0:
            continue
        price = current_prices.get(ticker)
        if price is None or price <= 0:
            logger.warning("No price for %s — skipping sell", ticker)
            continue
        order = broker.submit_order(ticker, "SELL", qty, price)
        orders.append(order)
        logger.info("SELL %s qty=%.2f price=%.2f status=%s", ticker, qty, price, order.status)

    # Recalculate after sells
    portfolio_value = broker.get_portfolio_value(current_prices)
    cash = broker.get_cash()
    exposure = broker.gross_exposure(current_prices)

    # Check exposure limit before buying
    if not check_exposure_limit(exposure, portfolio_value):
        logger.warning("Exposure limit reached — skipping buys")
        return orders

    # Determine how many positions we can add
    positions_after_sells = len(broker.get_positions())
    buy_slots = max(0, max_positions - positions_after_sells)

    if buy_slots == 0:
        logger.info("Max positions reached — skipping buys")
        return orders

    # Limit buys to available slots
    buys = tickers_to_buy[:buy_slots]
    num_target = max(len(buys), 1)

    for ticker in buys:
        price = current_prices.get(ticker)
        if price is None or price <= 0:
            logger.warning("No price for %s — skipping buy", ticker)
            continue

        qty_float = compute_order_quantity(
            ticker=ticker,
            price=price,
            portfolio_value=portfolio_value,
            cash_available=cash,
            num_target_positions=num_target,
            sizing_config=sizing_config,
        )

        # Whole shares only (floor)
        qty = math.floor(qty_float)
        if qty <= 0:
            logger.info("Computed qty=0 for %s at price=%.2f — skipping", ticker, price)
            continue

        order = broker.submit_order(ticker, "BUY", qty, price)
        orders.append(order)
        logger.info("BUY %s qty=%d price=%.2f status=%s", ticker, qty, price, order.status)

        # Update cash after buy for subsequent iterations
        if order.status == "filled":
            cash = broker.get_cash()

    return orders
