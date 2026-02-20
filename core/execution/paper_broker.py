"""Paper trading broker."""

from __future__ import annotations

from core.backtesting.cost_model import CostModel, get_cost_model
from core.execution.broker_base import BrokerBase, Order, Position
from core.execution.guard import ensure_paper_mode


class PaperBroker(BrokerBase):
    """In-memory paper trading broker with immediate fill simulation."""

    def __init__(self, initial_cash: float | None = None, cost_model: CostModel | None = None):
        ensure_paper_mode()
        from core.config import get_settings

        self._cash = initial_cash if initial_cash is not None else get_settings().PAPER_INITIAL_CASH
        self._cost_model = cost_model if cost_model is not None else get_cost_model()
        self._positions: dict[str, dict] = {}  # ticker -> {quantity, avg_entry_price}
        self._orders: list[Order] = []
        self._realized_pnl: float = 0.0

    def submit_order(self, ticker: str, side: str, quantity: float, price: float) -> Order:
        ensure_paper_mode()
        side = side.upper()

        fill_price = self._cost_model.apply_costs(price, quantity, side)
        commission = self._cost_model.trade_commission()

        if side == "BUY":
            total_cost = fill_price * quantity + commission
            if total_cost > self._cash:
                order = Order(
                    ticker=ticker, side=side, quantity=quantity,
                    price=fill_price, status="rejected",
                )
                self._orders.append(order)
                return order

            self._cash -= total_cost

            if ticker in self._positions:
                pos = self._positions[ticker]
                old_qty = pos["quantity"]
                old_avg = pos["avg_entry_price"]
                new_qty = old_qty + quantity
                pos["avg_entry_price"] = (old_avg * old_qty + fill_price * quantity) / new_qty
                pos["quantity"] = new_qty
            else:
                self._positions[ticker] = {
                    "quantity": quantity,
                    "avg_entry_price": fill_price,
                }

        elif side == "SELL":
            if ticker not in self._positions or self._positions[ticker]["quantity"] < quantity:
                order = Order(
                    ticker=ticker, side=side, quantity=quantity,
                    price=fill_price, status="rejected",
                )
                self._orders.append(order)
                return order

            pos = self._positions[ticker]
            proceeds = fill_price * quantity - commission
            self._cash += proceeds

            trade_pnl = (fill_price - pos["avg_entry_price"]) * quantity - commission
            self._realized_pnl += trade_pnl

            pos["quantity"] -= quantity
            if pos["quantity"] <= 1e-9:
                del self._positions[ticker]

        order = Order(
            ticker=ticker, side=side, quantity=quantity,
            price=fill_price, status="filled",
        )
        self._orders.append(order)
        return order

    def get_positions(self) -> list[Position]:
        ensure_paper_mode()
        return [
            Position(
                ticker=ticker,
                quantity=pos["quantity"],
                avg_entry_price=pos["avg_entry_price"],
            )
            for ticker, pos in self._positions.items()
        ]

    def get_cash(self) -> float:
        ensure_paper_mode()
        return self._cash

    def get_portfolio_value(self, current_prices: dict[str, float]) -> float:
        ensure_paper_mode()
        value = self._cash
        for ticker, pos in self._positions.items():
            price = current_prices.get(ticker, pos["avg_entry_price"])
            value += pos["quantity"] * price
        return value

    def get_orders(self) -> list[Order]:
        ensure_paper_mode()
        return list(self._orders)

    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl

    def unrealized_pnl(self, current_prices: dict[str, float]) -> float:
        """Compute total unrealized PnL given current market prices."""
        total = 0.0
        for ticker, pos in self._positions.items():
            price = current_prices.get(ticker, pos["avg_entry_price"])
            total += (price - pos["avg_entry_price"]) * pos["quantity"]
        return total

    def gross_exposure(self, current_prices: dict[str, float]) -> float:
        """Compute gross exposure as sum of absolute position market values."""
        total = 0.0
        for ticker, pos in self._positions.items():
            price = current_prices.get(ticker, pos["avg_entry_price"])
            total += abs(pos["quantity"] * price)
        return total
