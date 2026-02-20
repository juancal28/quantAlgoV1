"""Base broker interface."""

from __future__ import annotations

import abc
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Order:
    """A single order submitted to a broker."""

    ticker: str
    side: str  # "BUY" or "SELL"
    quantity: float
    price: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "filled"  # filled | rejected | pending


@dataclass
class Position:
    """A current holding in the portfolio."""

    ticker: str
    quantity: float
    avg_entry_price: float
    market_value: float = 0.0
    unrealized_pnl: float = 0.0


class BrokerBase(abc.ABC):
    """Abstract base class for broker adapters."""

    @abc.abstractmethod
    def submit_order(self, ticker: str, side: str, quantity: float, price: float) -> Order:
        """Submit an order and return the filled/rejected Order."""
        ...

    @abc.abstractmethod
    def get_positions(self) -> list[Position]:
        """Return all current positions."""
        ...

    @abc.abstractmethod
    def get_cash(self) -> float:
        """Return available cash balance."""
        ...

    @abc.abstractmethod
    def get_portfolio_value(self, current_prices: dict[str, float]) -> float:
        """Return total portfolio value (cash + positions at current prices)."""
        ...

    @abc.abstractmethod
    def get_orders(self) -> list[Order]:
        """Return all orders submitted in this session."""
        ...
