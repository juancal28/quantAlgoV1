"""Trade cost model: commission, slippage, and spread — delegating to C++ implementation."""

from __future__ import annotations

from _quant_core import CppCostModel


class CostModel:
    """Encapsulates all trade cost parameters. Delegates to C++ CppCostModel."""

    def __init__(
        self,
        commission_per_trade: float,
        slippage_bps: float,
        spread_bps: float,
    ):
        self.commission_per_trade = commission_per_trade
        self.slippage_bps = slippage_bps
        self.spread_bps = spread_bps
        self._cpp = CppCostModel(commission_per_trade, slippage_bps, spread_bps)

    def apply_costs(self, price: float, quantity: float, side: str) -> float:
        """Return the adjusted fill price after slippage and spread.

        BUY fills at a higher price (costs more), SELL at a lower price (receives less).
        """
        return self._cpp.apply_costs(price, quantity, side)

    def trade_commission(self) -> float:
        """Flat commission per trade."""
        return self._cpp.trade_commission()

    def total_cost_for_trade(self, price: float, quantity: float, side: str) -> float:
        """Total dollar impact of a trade including commission.

        Returns a positive value representing the cost.
        """
        return self._cpp.total_cost_for_trade(price, quantity, side)


def get_cost_model() -> CostModel:
    """Factory: build a CostModel from application config."""
    from core.config import get_settings

    s = get_settings()
    return CostModel(
        commission_per_trade=s.BACKTEST_COMMISSION_PER_TRADE,
        slippage_bps=s.BACKTEST_SLIPPAGE_BPS,
        spread_bps=s.BACKTEST_SPREAD_BPS,
    )
