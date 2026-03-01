"""Backtest metrics calculation — delegating to C++."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from _quant_core import cpp_compute_metrics, cpp_passes_thresholds


@dataclass
class BacktestMetrics:
    """All required performance metrics from a backtest run."""

    cagr: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    turnover: float
    avg_trade_return: float


def compute_metrics(
    equity_curve: pd.Series,
    trade_returns: list[float],
) -> BacktestMetrics:
    """Compute all 6 performance metrics from an equity curve and trade list.

    Extracts raw arrays and delegates computation to C++.
    """
    if equity_curve.empty or len(equity_curve) < 2:
        return BacktestMetrics(
            cagr=0.0,
            sharpe=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            turnover=0.0,
            avg_trade_return=0.0,
        )

    equity_values = equity_curve.values.tolist()
    cpp_m = cpp_compute_metrics(equity_values, trade_returns)

    return BacktestMetrics(
        cagr=cpp_m.cagr,
        sharpe=cpp_m.sharpe,
        max_drawdown=cpp_m.max_drawdown,
        win_rate=cpp_m.win_rate,
        turnover=cpp_m.turnover,
        avg_trade_return=cpp_m.avg_trade_return,
    )


def passes_thresholds(metrics: BacktestMetrics) -> bool:
    """Check whether metrics meet activation thresholds from config."""
    from core.config import get_settings

    s = get_settings()

    # Create a C++ metrics object for the threshold check
    from _quant_core import CppBacktestMetrics
    cpp_m = CppBacktestMetrics()
    cpp_m.sharpe = metrics.sharpe
    cpp_m.max_drawdown = metrics.max_drawdown
    cpp_m.win_rate = metrics.win_rate

    return cpp_passes_thresholds(
        cpp_m,
        s.BACKTEST_MIN_SHARPE,
        s.BACKTEST_MAX_DRAWDOWN,
        s.BACKTEST_MIN_WIN_RATE,
    )
