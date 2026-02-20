"""Tests for the signal evaluation engine."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.execution.broker_base import Order, Position
from core.execution.signal_evaluator import (
    evaluate_news_sentiment_signal,
    evaluate_volatility_filter,
    execute_signals,
    generate_signals_from_definition,
    reconcile_positions,
)
from core.storage.models import MarketBar, NewsDocument


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_news_doc(
    tickers: list[str],
    sentiment_score: float | None,
    minutes_ago: int = 10,
) -> NewsDocument:
    """Create a NewsDocument for testing."""
    now = datetime.now(timezone.utc)
    return NewsDocument(
        id=uuid.uuid4(),
        source="test",
        source_url=f"https://test.com/{uuid.uuid4()}",
        title="Test Article",
        published_at=now - timedelta(minutes=minutes_ago),
        fetched_at=now,
        content="Test content",
        content_hash=str(uuid.uuid4()),
        metadata_={"tickers": tickers},
        sentiment_score=sentiment_score,
        sentiment_label="positive" if sentiment_score and sentiment_score > 0.5 else "neutral",
    )


class FakeBroker:
    """Minimal fake broker for testing execute_signals."""

    def __init__(self, cash: float = 100_000, positions: dict | None = None):
        self._cash = cash
        self._positions = positions or {}  # {ticker: {quantity, avg_entry_price}}
        self._orders: list[Order] = []

    def get_positions(self) -> list[Position]:
        return [
            Position(ticker=t, quantity=p["quantity"], avg_entry_price=p["avg_entry_price"])
            for t, p in self._positions.items()
        ]

    def get_cash(self) -> float:
        return self._cash

    def get_portfolio_value(self, current_prices: dict[str, float]) -> float:
        value = self._cash
        for t, p in self._positions.items():
            price = current_prices.get(t, p["avg_entry_price"])
            value += p["quantity"] * price
        return value

    def get_orders(self) -> list[Order]:
        return list(self._orders)

    def gross_exposure(self, current_prices: dict[str, float]) -> float:
        total = 0.0
        for t, p in self._positions.items():
            price = current_prices.get(t, p["avg_entry_price"])
            total += abs(p["quantity"] * price)
        return total

    @property
    def realized_pnl(self) -> float:
        return 0.0

    def unrealized_pnl(self, current_prices: dict[str, float]) -> float:
        return 0.0

    def submit_order(self, ticker: str, side: str, quantity: float, price: float) -> Order:
        order = Order(ticker=ticker, side=side.upper(), quantity=quantity, price=price, status="filled")
        self._orders.append(order)

        if side.upper() == "SELL" and ticker in self._positions:
            self._positions[ticker]["quantity"] -= quantity
            self._cash += quantity * price
            if self._positions[ticker]["quantity"] <= 0:
                del self._positions[ticker]
        elif side.upper() == "BUY":
            self._cash -= quantity * price
            if ticker in self._positions:
                self._positions[ticker]["quantity"] += quantity
            else:
                self._positions[ticker] = {"quantity": quantity, "avg_entry_price": price}

        return order


# ---------------------------------------------------------------------------
# evaluate_news_sentiment_signal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEvaluateNewsSentimentSignal:

    async def test_threshold_filtering(self, db_session, mock_settings):
        """Only tickers with avg sentiment above threshold are returned."""
        mock_settings("TRADING_MODE", "paper")

        # Two docs for SPY: avg = (0.8 + 0.7) / 2 = 0.75 > 0.65
        db_session.add(_make_news_doc(["SPY"], 0.8))
        db_session.add(_make_news_doc(["SPY"], 0.7))
        # One doc for AAPL: avg = 0.3 < 0.65
        db_session.add(_make_news_doc(["AAPL"], 0.3))
        await db_session.flush()

        signal_config = {"lookback_minutes": 60, "threshold": 0.65}
        result = await evaluate_news_sentiment_signal(
            db_session, signal_config, ["SPY", "AAPL"]
        )

        assert "SPY" in result
        assert result["SPY"] == pytest.approx(0.75)
        assert "AAPL" not in result

    async def test_per_ticker_grouping(self, db_session, mock_settings):
        """Docs with multiple tickers count for each ticker separately."""
        mock_settings("TRADING_MODE", "paper")

        db_session.add(_make_news_doc(["SPY", "QQQ"], 0.9))
        db_session.add(_make_news_doc(["QQQ"], 0.4))
        await db_session.flush()

        signal_config = {"lookback_minutes": 60, "threshold": 0.65}
        result = await evaluate_news_sentiment_signal(
            db_session, signal_config, ["SPY", "QQQ"]
        )

        # SPY: avg = 0.9 > 0.65
        assert "SPY" in result
        # QQQ: avg = (0.9 + 0.4) / 2 = 0.65, exactly at threshold -> passes
        assert "QQQ" in result

    async def test_empty_news(self, db_session, mock_settings):
        """No news docs -> empty result."""
        mock_settings("TRADING_MODE", "paper")

        signal_config = {"lookback_minutes": 60, "threshold": 0.65}
        result = await evaluate_news_sentiment_signal(
            db_session, signal_config, ["SPY"]
        )
        assert result == {}

    async def test_lookback_window(self, db_session, mock_settings):
        """Docs outside the lookback window are excluded."""
        mock_settings("TRADING_MODE", "paper")

        # Doc published 120 minutes ago, lookback is 60 minutes
        db_session.add(_make_news_doc(["SPY"], 0.9, minutes_ago=120))
        await db_session.flush()

        signal_config = {"lookback_minutes": 60, "threshold": 0.5}
        result = await evaluate_news_sentiment_signal(
            db_session, signal_config, ["SPY"]
        )
        assert result == {}

    async def test_ignores_tickers_outside_universe(self, db_session, mock_settings):
        """Tickers in docs but not in universe are ignored."""
        mock_settings("TRADING_MODE", "paper")

        db_session.add(_make_news_doc(["TSLA"], 0.9))
        await db_session.flush()

        signal_config = {"lookback_minutes": 60, "threshold": 0.5}
        result = await evaluate_news_sentiment_signal(
            db_session, signal_config, ["SPY"]
        )
        assert result == {}

    async def test_null_sentiment_score_skipped(self, db_session, mock_settings):
        """Docs with null sentiment_score are skipped."""
        mock_settings("TRADING_MODE", "paper")

        db_session.add(_make_news_doc(["SPY"], None))
        await db_session.flush()

        signal_config = {"lookback_minutes": 60, "threshold": 0.5}
        result = await evaluate_news_sentiment_signal(
            db_session, signal_config, ["SPY"]
        )
        assert result == {}


# ---------------------------------------------------------------------------
# evaluate_volatility_filter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEvaluateVolatilityFilter:

    async def test_passes_below_max_vix(self, db_session, mock_settings):
        """Filter passes when VIXY price is below max_vix."""
        mock_settings("TRADING_MODE", "paper")

        bar = MarketBar(
            id=uuid.uuid4(), ticker="VIXY", timeframe="1Day",
            bar_time=datetime.now(timezone.utc) - timedelta(minutes=5),
            open=20.0, high=21.0, low=19.0, close=20.5,
            volume=1000000, fetched_at=datetime.now(timezone.utc),
        )
        db_session.add(bar)
        await db_session.flush()

        result = await evaluate_volatility_filter(db_session, {"max_vix": 25})
        assert result is True

    async def test_fails_above_max_vix(self, db_session, mock_settings):
        """Filter fails when VIXY price exceeds max_vix."""
        mock_settings("TRADING_MODE", "paper")

        bar = MarketBar(
            id=uuid.uuid4(), ticker="VIXY", timeframe="1Day",
            bar_time=datetime.now(timezone.utc) - timedelta(minutes=5),
            open=30.0, high=31.0, low=29.0, close=30.5,
            volume=1000000, fetched_at=datetime.now(timezone.utc),
        )
        db_session.add(bar)
        await db_session.flush()

        result = await evaluate_volatility_filter(db_session, {"max_vix": 25})
        assert result is False

    async def test_defaults_to_pass_when_no_data(self, db_session, mock_settings):
        """Filter defaults to True (optimistic) when no VIXY data available."""
        mock_settings("TRADING_MODE", "paper")

        result = await evaluate_volatility_filter(db_session, {"max_vix": 25})
        assert result is True


# ---------------------------------------------------------------------------
# generate_signals_from_definition
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGenerateSignalsFromDefinition:

    async def test_long_signals_for_positive_sentiment(self, db_session, mock_settings):
        """Tickers with positive sentiment get long signals."""
        mock_settings("TRADING_MODE", "paper")

        db_session.add(_make_news_doc(["SPY"], 0.9))
        db_session.add(_make_news_doc(["QQQ"], 0.2))
        await db_session.flush()

        definition = {
            "universe": ["SPY", "QQQ"],
            "signals": [
                {"type": "news_sentiment", "lookback_minutes": 60, "threshold": 0.65, "direction": "long"},
            ],
        }
        current_prices = {"SPY": 450.0, "QQQ": 380.0}

        result = await generate_signals_from_definition(db_session, definition, current_prices)
        assert result["SPY"] == "long"
        assert result["QQQ"] == "flat"

    async def test_all_flat_when_volatility_filter_trips(self, db_session, mock_settings):
        """All tickers go flat when volatility filter fails."""
        mock_settings("TRADING_MODE", "paper")

        # VIXY above max_vix
        bar = MarketBar(
            id=uuid.uuid4(), ticker="VIXY", timeframe="1Day",
            bar_time=datetime.now(timezone.utc) - timedelta(minutes=5),
            open=30.0, high=31.0, low=29.0, close=30.5,
            volume=1000000, fetched_at=datetime.now(timezone.utc),
        )
        db_session.add(bar)
        db_session.add(_make_news_doc(["SPY"], 0.9))
        await db_session.flush()

        definition = {
            "universe": ["SPY"],
            "signals": [
                {"type": "volatility_filter", "max_vix": 25},
                {"type": "news_sentiment", "lookback_minutes": 60, "threshold": 0.5, "direction": "long"},
            ],
        }

        result = await generate_signals_from_definition(
            db_session, definition, {"SPY": 450.0}
        )
        assert result["SPY"] == "flat"

    async def test_tickers_without_prices_excluded(self, db_session, mock_settings):
        """Tickers not in current_prices are excluded from results."""
        mock_settings("TRADING_MODE", "paper")

        definition = {
            "universe": ["SPY", "QQQ"],
            "signals": [],
        }

        result = await generate_signals_from_definition(
            db_session, definition, {"SPY": 450.0}
        )
        assert "SPY" in result
        assert "QQQ" not in result


# ---------------------------------------------------------------------------
# reconcile_positions
# ---------------------------------------------------------------------------

class TestReconcilePositions:

    def test_buy_new_tickers(self):
        """Should buy tickers with long signal not currently held."""
        signals = {"SPY": "long", "QQQ": "long"}
        current = {}
        to_buy, to_sell = reconcile_positions(signals, current)
        assert set(to_buy) == {"SPY", "QQQ"}
        assert to_sell == []

    def test_sell_old_tickers(self):
        """Should sell tickers held but flat signal."""
        signals = {"SPY": "flat"}
        current = {"SPY": 10.0}
        to_buy, to_sell = reconcile_positions(signals, current)
        assert to_buy == []
        assert to_sell == ["SPY"]

    def test_no_op_when_aligned(self):
        """No action needed when positions match signals."""
        signals = {"SPY": "long"}
        current = {"SPY": 10.0}
        to_buy, to_sell = reconcile_positions(signals, current)
        assert to_buy == []
        assert to_sell == []

    def test_all_flat_sells_everything(self):
        """All flat signals should sell all positions."""
        signals = {"SPY": "flat", "QQQ": "flat"}
        current = {"SPY": 10.0, "QQQ": 5.0}
        to_buy, to_sell = reconcile_positions(signals, current)
        assert to_buy == []
        assert set(to_sell) == {"SPY", "QQQ"}

    def test_held_ticker_not_in_signals_sold(self):
        """Held ticker absent from signals should be sold."""
        signals = {"SPY": "long"}
        current = {"SPY": 10.0, "AAPL": 5.0}
        to_buy, to_sell = reconcile_positions(signals, current)
        assert to_buy == []
        assert to_sell == ["AAPL"]


# ---------------------------------------------------------------------------
# execute_signals
# ---------------------------------------------------------------------------

class TestExecuteSignals:

    def test_sells_before_buys(self, mock_settings):
        """SELLs should execute before BUYs."""
        mock_settings("RISK_MAX_GROSS_EXPOSURE", "1.0")
        mock_settings("RISK_MAX_POSITION_PCT", "0.10")
        mock_settings("RISK_MAX_TRADES_PER_HOUR", "30")
        mock_settings("PAPER_INITIAL_CASH", "100000")

        broker = FakeBroker(
            cash=50_000,
            positions={"AAPL": {"quantity": 10, "avg_entry_price": 150.0}},
        )
        signals = {"SPY": "long", "AAPL": "flat"}
        prices = {"SPY": 450.0, "AAPL": 155.0}
        definition = {
            "rules": {
                "max_positions": 5,
                "position_sizing": {"type": "equal_weight", "max_position_pct": 0.10},
            }
        }

        orders = execute_signals(broker, signals, prices, definition, circuit_breaker_tripped=False)

        # First order should be SELL AAPL, then BUY SPY
        assert len(orders) >= 2
        sell_orders = [o for o in orders if o.side == "SELL"]
        buy_orders = [o for o in orders if o.side == "BUY"]
        assert len(sell_orders) == 1
        assert sell_orders[0].ticker == "AAPL"
        assert len(buy_orders) == 1
        assert buy_orders[0].ticker == "SPY"

    def test_respects_max_positions(self, mock_settings):
        """Should not buy more tickers than max_positions allows."""
        mock_settings("RISK_MAX_GROSS_EXPOSURE", "1.0")
        mock_settings("RISK_MAX_POSITION_PCT", "0.50")
        mock_settings("RISK_MAX_TRADES_PER_HOUR", "30")
        mock_settings("PAPER_INITIAL_CASH", "100000")

        broker = FakeBroker(
            cash=100_000,
            positions={
                "AAPL": {"quantity": 10, "avg_entry_price": 150.0},
                "MSFT": {"quantity": 10, "avg_entry_price": 350.0},
            },
        )
        signals = {"AAPL": "long", "MSFT": "long", "SPY": "long", "QQQ": "long", "GOOGL": "long"}
        prices = {"AAPL": 150.0, "MSFT": 350.0, "SPY": 450.0, "QQQ": 380.0, "GOOGL": 160.0}
        definition = {"rules": {"max_positions": 3}}  # Only 1 slot available

        orders = execute_signals(broker, signals, prices, definition, circuit_breaker_tripped=False)

        # Already holding 2, max 3, so only 1 buy allowed
        buy_orders = [o for o in orders if o.side == "BUY"]
        assert len(buy_orders) <= 1

    def test_skips_on_circuit_breaker(self, mock_settings):
        """No orders when circuit breaker is tripped."""
        mock_settings("RISK_MAX_GROSS_EXPOSURE", "1.0")
        mock_settings("RISK_MAX_TRADES_PER_HOUR", "30")
        mock_settings("PAPER_INITIAL_CASH", "100000")

        broker = FakeBroker(cash=100_000)
        signals = {"SPY": "long"}
        prices = {"SPY": 450.0}
        definition = {"rules": {"max_positions": 5}}

        orders = execute_signals(broker, signals, prices, definition, circuit_breaker_tripped=True)
        assert orders == []

    def test_whole_shares_only(self, mock_settings):
        """Only whole shares (floor) should be ordered."""
        mock_settings("RISK_MAX_GROSS_EXPOSURE", "1.0")
        mock_settings("RISK_MAX_POSITION_PCT", "0.10")
        mock_settings("RISK_MAX_TRADES_PER_HOUR", "30")
        mock_settings("PAPER_INITIAL_CASH", "100000")

        broker = FakeBroker(cash=100_000)
        signals = {"SPY": "long"}
        prices = {"SPY": 450.0}
        definition = {
            "rules": {
                "max_positions": 5,
                "position_sizing": {"type": "equal_weight", "max_position_pct": 0.10},
            }
        }

        orders = execute_signals(broker, signals, prices, definition, circuit_breaker_tripped=False)

        buy_orders = [o for o in orders if o.side == "BUY"]
        for o in buy_orders:
            assert o.quantity == int(o.quantity)  # whole shares

    def test_no_action_when_aligned(self, mock_settings):
        """No orders when positions already match signals."""
        mock_settings("RISK_MAX_GROSS_EXPOSURE", "1.0")
        mock_settings("RISK_MAX_TRADES_PER_HOUR", "30")
        mock_settings("PAPER_INITIAL_CASH", "100000")

        broker = FakeBroker(
            cash=50_000,
            positions={"SPY": {"quantity": 10, "avg_entry_price": 450.0}},
        )
        signals = {"SPY": "long"}
        prices = {"SPY": 450.0}
        definition = {"rules": {"max_positions": 5}}

        orders = execute_signals(broker, signals, prices, definition, circuit_breaker_tripped=False)
        assert orders == []

    def test_skips_when_trade_rate_exceeded(self, mock_settings):
        """No orders when trade rate limit is exceeded."""
        mock_settings("RISK_MAX_GROSS_EXPOSURE", "1.0")
        mock_settings("RISK_MAX_TRADES_PER_HOUR", "2")  # Very low limit
        mock_settings("PAPER_INITIAL_CASH", "100000")

        broker = FakeBroker(cash=100_000)
        # Pre-fill some orders to exceed the rate limit
        broker._orders = [
            Order(ticker="X", side="BUY", quantity=1, price=1.0),
            Order(ticker="Y", side="BUY", quantity=1, price=1.0),
        ]
        signals = {"SPY": "long"}
        prices = {"SPY": 450.0}
        definition = {"rules": {"max_positions": 5}}

        orders = execute_signals(broker, signals, prices, definition, circuit_breaker_tripped=False)
        assert orders == []
