"""Backtesting engine — adapter pattern with C++ v1 implementation."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from _quant_core import CppBacktestEngine, CppCostModel, CppSignalConfig

from core.backtesting.cost_model import CostModel, get_cost_model
from core.backtesting.metrics import BacktestMetrics, compute_metrics, passes_thresholds


@dataclass
class Trade:
    """A single executed trade."""

    ticker: str
    side: str
    quantity: float
    price: float
    bar_time: datetime
    pnl: float = 0.0


@dataclass
class BacktestResult:
    """Complete output of a backtest run."""

    metrics: BacktestMetrics
    passed: bool
    equity_curve: pd.Series
    trades: list[Trade] = field(default_factory=list)


class BacktestEngine(abc.ABC):
    """Abstract base for backtesting engines (adapter pattern)."""

    @abc.abstractmethod
    def run(
        self,
        definition: dict,
        price_data: dict[str, pd.DataFrame],
        initial_cash: float,
        cost_model: CostModel,
    ) -> BacktestResult:
        """Run a backtest and return the result."""
        ...


class BuiltinEngine(BacktestEngine):
    """Built-in v1 backtest engine — delegates to C++ for performance.

    Converts DataFrames to raw arrays, calls C++ engine, reconstructs
    BacktestResult with pd.Series equity curve and Python Trade dataclasses.
    """

    def run(
        self,
        definition: dict,
        price_data: dict[str, pd.DataFrame],
        initial_cash: float,
        cost_model: CostModel,
    ) -> BacktestResult:
        universe = definition["universe"]
        signals_cfg = definition.get("signals", [])
        rules = definition.get("rules", {})
        max_positions = rules.get("max_positions", len(universe))
        sizing = rules.get("position_sizing", {})
        max_pos_pct = sizing.get("max_position_pct", 0.10)

        # Validate that we have data for every ticker in the universe
        for ticker in universe:
            if ticker not in price_data:
                raise ValueError(f"No price data for ticker '{ticker}'")
            if len(price_data[ticker]) < 2:
                raise ValueError(
                    f"Insufficient data for ticker '{ticker}': "
                    f"need >= 2 bars, got {len(price_data[ticker])}"
                )

        # Convert DataFrames to C++ BarData format
        from _quant_core import CppBarData
        cpp_price_data: dict[str, list] = {}
        for ticker in universe:
            df = price_data[ticker]
            bars = []
            for idx, row in df.iterrows():
                timestamp_epoch = int(idx.timestamp()) if hasattr(idx, 'timestamp') else 0
                bars.append(CppBarData(
                    open=float(row["open"]),
                    high=float(row.get("high", row["open"])),
                    low=float(row.get("low", row["open"])),
                    close=float(row.get("close", row["open"])),
                    volume=int(row.get("volume", 0)),
                    timestamp_epoch=timestamp_epoch,
                ))
            cpp_price_data[ticker] = bars

        # Convert signal configs to C++ format
        cpp_signals = []
        for sig in signals_cfg:
            sig_type = sig.get("type", "")
            params: dict[str, float] = {}
            direction = sig.get("direction", "long")
            for k, v in sig.items():
                if k not in ("type", "direction"):
                    try:
                        params[k] = float(v)
                    except (ValueError, TypeError):
                        pass
            cpp_signals.append(CppSignalConfig(sig_type, params, direction))

        # Create C++ cost model
        cpp_cm = CppCostModel(
            cost_model.commission_per_trade,
            cost_model.slippage_bps,
            cost_model.spread_bps,
        )

        # Get threshold config
        from core.config import get_settings
        s = get_settings()

        # Run C++ engine
        engine = CppBacktestEngine()
        cpp_result = engine.run(
            universe, cpp_signals, max_positions, max_pos_pct,
            cpp_price_data, initial_cash, cpp_cm,
            s.BACKTEST_MIN_SHARPE, s.BACKTEST_MAX_DRAWDOWN, s.BACKTEST_MIN_WIN_RATE,
        )

        # Reconstruct equity curve as pd.Series with datetime index
        equity_dates = [
            datetime.fromtimestamp(ts) for ts in cpp_result.equity_dates
        ]
        equity_curve = pd.Series(
            cpp_result.equity_values, index=equity_dates, dtype=float,
        )

        # Reconstruct Trade dataclasses
        trades = [
            Trade(
                ticker=t.ticker,
                side=t.side,
                quantity=t.quantity,
                price=t.price,
                bar_time=datetime.fromtimestamp(t.bar_time_epoch),
                pnl=t.pnl,
            )
            for t in cpp_result.trades
        ]

        # Reconstruct BacktestMetrics
        metrics = BacktestMetrics(
            cagr=cpp_result.metrics.cagr,
            sharpe=cpp_result.metrics.sharpe,
            max_drawdown=cpp_result.metrics.max_drawdown,
            win_rate=cpp_result.metrics.win_rate,
            turnover=cpp_result.metrics.turnover,
            avg_trade_return=cpp_result.metrics.avg_trade_return,
        )

        return BacktestResult(
            metrics=metrics,
            passed=cpp_result.passed,
            equity_curve=equity_curve,
            trades=trades,
        )


def run_backtest(
    definition_dict: dict,
    price_data: dict[str, pd.DataFrame],
    initial_cash: float | None = None,
    cost_model: CostModel | None = None,
    engine: BacktestEngine | None = None,
) -> BacktestResult:
    """Convenience function: run a backtest with sensible defaults from config."""
    from core.config import get_settings

    if initial_cash is None:
        initial_cash = get_settings().PAPER_INITIAL_CASH
    if cost_model is None:
        cost_model = get_cost_model()
    if engine is None:
        engine = BuiltinEngine()

    return engine.run(definition_dict, price_data, initial_cash, cost_model)
