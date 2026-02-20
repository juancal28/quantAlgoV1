"""Alpaca paper trading broker."""

from __future__ import annotations

from core.execution.broker_base import BrokerBase, Order, Position
from core.execution.guard import ensure_paper_mode


class AlpacaPaperBroker(BrokerBase):
    """Guard-enforced stub for Alpaca paper trading.

    Calls ensure_paper_mode() on construction and every method.
    Not yet implemented — submit_order raises NotImplementedError.
    """

    def __init__(self):
        ensure_paper_mode()

    def submit_order(self, ticker: str, side: str, quantity: float, price: float) -> Order:
        ensure_paper_mode()
        raise NotImplementedError("AlpacaPaperBroker.submit_order is not yet implemented")

    def get_positions(self) -> list[Position]:
        ensure_paper_mode()
        return []

    def get_cash(self) -> float:
        ensure_paper_mode()
        return 0.0

    def get_portfolio_value(self, current_prices: dict[str, float]) -> float:
        ensure_paper_mode()
        return 0.0

    def get_orders(self) -> list[Order]:
        ensure_paper_mode()
        return []
