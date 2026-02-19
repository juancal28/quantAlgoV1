"""Trade cost model: commission, slippage, and spread."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    """Encapsulates all trade cost parameters."""

    commission_per_trade: float
    slippage_bps: float
    spread_bps: float

    def apply_costs(self, price: float, quantity: float, side: str) -> float:
        """Return the adjusted fill price after slippage and spread.

        BUY fills at a higher price (costs more), SELL at a lower price (receives less).
        """
        impact_bps = self.slippage_bps + self.spread_bps / 2.0
        if side.upper() == "BUY":
            return price * (1.0 + impact_bps / 10_000.0)
        else:
            return price * (1.0 - impact_bps / 10_000.0)

    def trade_commission(self) -> float:
        """Flat commission per trade."""
        return self.commission_per_trade

    def total_cost_for_trade(self, price: float, quantity: float, side: str) -> float:
        """Total dollar impact of a trade including commission.

        Returns a positive value representing the cost.
        """
        fill_price = self.apply_costs(price, quantity, side)
        price_impact = abs(fill_price - price) * abs(quantity)
        return price_impact + self.commission_per_trade


def get_cost_model() -> CostModel:
    """Factory: build a CostModel from application config."""
    from core.config import get_settings

    s = get_settings()
    return CostModel(
        commission_per_trade=s.BACKTEST_COMMISSION_PER_TRADE,
        slippage_bps=s.BACKTEST_SLIPPAGE_BPS,
        spread_bps=s.BACKTEST_SPREAD_BPS,
    )
