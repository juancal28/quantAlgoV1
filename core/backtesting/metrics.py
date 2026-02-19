"""Backtest metrics calculation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


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

    Args:
        equity_curve: Time-indexed series of portfolio value.
        trade_returns: List of per-trade percentage returns.

    Returns:
        BacktestMetrics with all fields populated (zeros for edge cases).
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

    # Daily returns
    daily_returns = equity_curve.pct_change().dropna()

    # CAGR
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0]
    n_days = len(equity_curve)
    n_years = n_days / 252.0
    if n_years > 0 and total_return > 0:
        cagr = total_return ** (1.0 / n_years) - 1.0
    else:
        cagr = 0.0

    # Sharpe ratio (annualized, risk-free = 0)
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    else:
        sharpe = 0.0

    # Max drawdown (returned as a positive fraction)
    cummax = equity_curve.cummax()
    drawdowns = (equity_curve - cummax) / cummax
    max_drawdown = abs(float(drawdowns.min()))

    # Win rate
    if trade_returns:
        wins = sum(1 for r in trade_returns if r > 0)
        win_rate = wins / len(trade_returns)
    else:
        win_rate = 0.0

    # Turnover proxy: mean absolute daily return
    turnover = float(daily_returns.abs().mean()) if len(daily_returns) > 0 else 0.0

    # Average trade return
    avg_trade_return = float(np.mean(trade_returns)) if trade_returns else 0.0

    return BacktestMetrics(
        cagr=cagr,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        turnover=turnover,
        avg_trade_return=avg_trade_return,
    )


def passes_thresholds(metrics: BacktestMetrics) -> bool:
    """Check whether metrics meet activation thresholds from config."""
    from core.config import get_settings

    s = get_settings()
    return bool(
        metrics.sharpe >= s.BACKTEST_MIN_SHARPE
        and metrics.max_drawdown <= s.BACKTEST_MAX_DRAWDOWN
        and metrics.win_rate >= s.BACKTEST_MIN_WIN_RATE
    )
