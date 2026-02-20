"""Alpaca paper trading broker."""

from __future__ import annotations

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from core.config import get_settings
from core.execution.broker_base import BrokerBase, Order, Position
from core.execution.guard import ensure_paper_mode
from core.logging import get_logger

logger = get_logger(__name__)


class AlpacaPaperBroker(BrokerBase):
    """Broker adapter that routes orders through Alpaca's paper trading API.

    Calls ensure_paper_mode() on construction and every method.
    """

    def __init__(self) -> None:
        ensure_paper_mode()
        s = get_settings()
        self._client = TradingClient(
            api_key=s.ALPACA_API_KEY,
            secret_key=s.ALPACA_API_SECRET,
            paper=True,
        )
        # Track realized PnL locally: Alpaca doesn't expose a single
        # session-level realized PnL field, so we compute from fills.
        self._entry_prices: dict[str, float] = {}
        self._realized_pnl_value: float = 0.0

    def submit_order(self, ticker: str, side: str, quantity: float, price: float) -> Order:
        ensure_paper_mode()
        side_upper = side.upper()
        alpaca_side = OrderSide.BUY if side_upper == "BUY" else OrderSide.SELL

        # Record entry price for realized PnL tracking on buys
        if side_upper == "BUY":
            self._entry_prices[ticker] = price

        req = MarketOrderRequest(
            symbol=ticker,
            qty=quantity,
            side=alpaca_side,
            time_in_force=TimeInForce.DAY,
        )
        alpaca_order = self._client.submit_order(req)

        fill_price = float(alpaca_order.filled_avg_price or price)

        # Track realized PnL on sells
        if side_upper == "SELL" and ticker in self._entry_prices:
            self._realized_pnl_value += (fill_price - self._entry_prices[ticker]) * quantity

        status = "filled" if alpaca_order.filled_qty and float(alpaca_order.filled_qty) > 0 else "pending"

        return Order(
            ticker=ticker,
            side=side_upper,
            quantity=quantity,
            price=fill_price,
            order_id=str(alpaca_order.id),
            status=status,
        )

    def get_positions(self) -> list[Position]:
        ensure_paper_mode()
        alpaca_positions = self._client.get_all_positions()
        return [
            Position(
                ticker=p.symbol,
                quantity=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                market_value=float(p.market_value),
                unrealized_pnl=float(p.unrealized_pl),
            )
            for p in alpaca_positions
        ]

    def get_cash(self) -> float:
        ensure_paper_mode()
        account = self._client.get_account()
        return float(account.cash)

    def get_portfolio_value(self, current_prices: dict[str, float]) -> float:
        ensure_paper_mode()
        # Alpaca calculates equity server-side; current_prices ignored.
        account = self._client.get_account()
        return float(account.equity)

    def get_orders(self) -> list[Order]:
        ensure_paper_mode()
        alpaca_orders = self._client.get_orders()
        return [
            Order(
                ticker=o.symbol,
                side=o.side.value.upper() if hasattr(o.side, "value") else str(o.side).upper(),
                quantity=float(o.qty),
                price=float(o.filled_avg_price or 0),
                order_id=str(o.id),
                status=str(o.status.value) if hasattr(o.status, "value") else str(o.status),
            )
            for o in alpaca_orders
        ]

    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl_value

    def unrealized_pnl(self, current_prices: dict[str, float]) -> float:
        """Sum unrealized PnL from Alpaca positions. Ignores current_prices."""
        ensure_paper_mode()
        positions = self._client.get_all_positions()
        return sum(float(p.unrealized_pl) for p in positions)

    def gross_exposure(self, current_prices: dict[str, float]) -> float:
        """Sum abs(market_value) from Alpaca positions. Ignores current_prices."""
        ensure_paper_mode()
        positions = self._client.get_all_positions()
        return sum(abs(float(p.market_value)) for p in positions)


def get_broker() -> BrokerBase:
    """Return the configured broker based on BROKER_PROVIDER setting."""
    from core.execution.paper_broker import PaperBroker

    provider = get_settings().BROKER_PROVIDER.lower()
    if provider == "alpaca":
        return AlpacaPaperBroker()
    return PaperBroker()
