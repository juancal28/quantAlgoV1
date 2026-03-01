"""Paper trading broker — wraps C++ CppPaperBroker for performance."""

from __future__ import annotations

from _quant_core import CppCostModel, CppPaperBroker

from core.backtesting.cost_model import CostModel, get_cost_model
from core.execution.broker_base import BrokerBase, Order, Position
from core.execution.guard import ensure_paper_mode


class PaperBroker(BrokerBase):
    """In-memory paper trading broker with immediate fill simulation.

    Delegates order matching, position management, and P&L tracking to the
    C++ CppPaperBroker for performance. PAPER_GUARD checks stay in Python.
    """

    def __init__(self, initial_cash: float | None = None, cost_model: CostModel | None = None):
        ensure_paper_mode()
        from core.config import get_settings

        cash = initial_cash if initial_cash is not None else get_settings().PAPER_INITIAL_CASH
        cm = cost_model if cost_model is not None else get_cost_model()

        cpp_cm = CppCostModel(cm.commission_per_trade, cm.slippage_bps, cm.spread_bps)
        self._cpp = CppPaperBroker(cash, cpp_cm)
        self._cost_model = cm

    def submit_order(self, ticker: str, side: str, quantity: float, price: float) -> Order:
        ensure_paper_mode()
        side = side.upper()
        cpp_order = self._cpp.submit_order(ticker, side, quantity, price)
        return Order(
            ticker=cpp_order.ticker,
            side=cpp_order.side,
            quantity=cpp_order.quantity,
            price=cpp_order.price,
            status=cpp_order.status,
        )

    def get_positions(self) -> list[Position]:
        ensure_paper_mode()
        return [
            Position(
                ticker=p.ticker,
                quantity=p.quantity,
                avg_entry_price=p.avg_entry_price,
            )
            for p in self._cpp.get_positions()
        ]

    def get_cash(self) -> float:
        ensure_paper_mode()
        return self._cpp.get_cash()

    def get_portfolio_value(self, current_prices: dict[str, float]) -> float:
        ensure_paper_mode()
        return self._cpp.get_portfolio_value(current_prices)

    def get_orders(self) -> list[Order]:
        ensure_paper_mode()
        return [
            Order(
                ticker=o.ticker,
                side=o.side,
                quantity=o.quantity,
                price=o.price,
                status=o.status,
            )
            for o in self._cpp.get_orders()
        ]

    @property
    def realized_pnl(self) -> float:
        return self._cpp.realized_pnl()

    def unrealized_pnl(self, current_prices: dict[str, float]) -> float:
        """Compute total unrealized PnL given current market prices."""
        return self._cpp.unrealized_pnl(current_prices)

    def gross_exposure(self, current_prices: dict[str, float]) -> float:
        """Compute gross exposure as sum of absolute position market values."""
        return self._cpp.gross_exposure(current_prices)
