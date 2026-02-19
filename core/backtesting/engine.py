"""Backtesting engine — adapter pattern with built-in v1 implementation."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

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
    """Built-in v1 backtest engine using bar OPEN prices only."""

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

        # Build combined date index across all tickers
        all_dates: set[datetime] = set()
        for df in price_data.values():
            all_dates.update(df.index.tolist())
        dates = sorted(all_dates)

        # Pre-compute signals for each ticker
        ticker_signals: dict[str, pd.Series] = {}
        for ticker in universe:
            df = price_data[ticker]
            ticker_signals[ticker] = self._generate_signals(
                df, signals_cfg, ticker
            )

        # Simulation state
        cash = initial_cash
        positions: dict[str, float] = {}  # ticker -> quantity
        entry_prices: dict[str, float] = {}  # ticker -> entry price
        trades: list[Trade] = []
        equity_values: list[float] = []
        equity_dates: list[datetime] = []

        for bar_time in dates:
            # Calculate current portfolio value
            portfolio_value = cash
            for t, qty in positions.items():
                if bar_time in price_data[t].index:
                    portfolio_value += qty * float(price_data[t].loc[bar_time, "open"])
                elif entry_prices.get(t):
                    portfolio_value += qty * entry_prices[t]

            equity_values.append(portfolio_value)
            equity_dates.append(bar_time)

            # Generate desired positions from signals
            desired_tickers: list[str] = []
            for ticker in universe:
                if bar_time not in price_data[ticker].index:
                    continue
                sig = ticker_signals[ticker]
                if bar_time in sig.index and sig.loc[bar_time] > 0:
                    desired_tickers.append(ticker)

            desired_tickers = desired_tickers[:max_positions]

            # Close positions no longer desired
            for ticker in list(positions.keys()):
                if ticker not in desired_tickers:
                    if bar_time not in price_data[ticker].index:
                        continue
                    qty = positions[ticker]
                    raw_price = float(price_data[ticker].loc[bar_time, "open"])
                    fill_price = cost_model.apply_costs(raw_price, qty, "SELL")
                    proceeds = qty * fill_price
                    cash += proceeds
                    commission = cost_model.trade_commission()
                    cash -= commission
                    trade_pnl = (fill_price - entry_prices[ticker]) * qty - commission
                    trades.append(Trade(
                        ticker=ticker,
                        side="SELL",
                        quantity=qty,
                        price=fill_price,
                        bar_time=bar_time,
                        pnl=trade_pnl,
                    ))
                    del positions[ticker]
                    del entry_prices[ticker]

            # Open new positions
            for ticker in desired_tickers:
                if ticker in positions:
                    continue
                if bar_time not in price_data[ticker].index:
                    continue
                raw_price = float(price_data[ticker].loc[bar_time, "open"])
                if raw_price <= 0:
                    continue
                # Position sizing: equal weight, capped at max_position_pct
                target_value = min(
                    portfolio_value / max(len(desired_tickers), 1),
                    portfolio_value * max_pos_pct,
                )
                target_value = min(target_value, cash)
                if target_value <= 0:
                    continue
                fill_price = cost_model.apply_costs(raw_price, 0, "BUY")
                qty = target_value / fill_price
                cost = qty * fill_price + cost_model.trade_commission()
                if cost > cash:
                    qty = (cash - cost_model.trade_commission()) / fill_price
                if qty <= 0:
                    continue
                cash -= qty * fill_price + cost_model.trade_commission()
                positions[ticker] = qty
                entry_prices[ticker] = fill_price
                trades.append(Trade(
                    ticker=ticker,
                    side="BUY",
                    quantity=qty,
                    price=fill_price,
                    bar_time=bar_time,
                ))

        # Build equity curve
        equity_curve = pd.Series(equity_values, index=equity_dates, dtype=float)

        # Compute trade returns (from closed trades only)
        trade_returns: list[float] = []
        for t in trades:
            if t.side == "SELL" and t.price > 0:
                # Find the matching buy entry
                entry = entry_prices.get(t.ticker)
                # Use pnl-based return since entry_prices is cleared on sell
                # pnl = (sell_price - entry_price) * qty - commission
                # Return as fraction of entry value
                if t.quantity > 0 and t.pnl != 0:
                    entry_value = t.price * t.quantity - t.pnl
                    if entry_value > 0:
                        trade_returns.append(t.pnl / entry_value)

        metrics = compute_metrics(equity_curve, trade_returns)
        passed = passes_thresholds(metrics)

        return BacktestResult(
            metrics=metrics,
            passed=passed,
            equity_curve=equity_curve,
            trades=trades,
        )

    def _generate_signals(
        self,
        df: pd.DataFrame,
        signals_cfg: list[dict],
        ticker: str,
    ) -> pd.Series:
        """Generate a combined signal series for a ticker.

        All signals use bar OPEN data only. Each signal is shifted by 1 bar
        to prevent lookahead bias.
        """
        combined = pd.Series(0.0, index=df.index)

        for sig in signals_cfg:
            sig_type = sig.get("type")

            if sig_type == "news_sentiment":
                lookback = sig.get("lookback_minutes", 240)
                # Convert minutes to approximate bar count (1Day bars = 390 min)
                lookback_bars = max(lookback // 390, 1)
                threshold = sig.get("threshold", 0.5)
                direction = sig.get("direction", "long")

                # Momentum proxy: rolling return over lookback window
                rolling_ret = df["open"].pct_change(periods=lookback_bars)
                # lookahead guard: shift(1)
                signal = rolling_ret.shift(1)
                if direction == "long":
                    combined += (signal > threshold * 0.01).astype(float)
                else:
                    combined += (signal < -threshold * 0.01).astype(float)

            elif sig_type == "volatility_filter":
                max_vix = sig.get("max_vix", 25)
                # 20-day rolling annualized vol from open prices
                rolling_vol = df["open"].pct_change().rolling(20).std() * np.sqrt(252)
                # lookahead guard: shift(1)
                vol_shifted = rolling_vol.shift(1)
                # Filter: pass signal when vol is below threshold
                vol_pct = max_vix / 100.0
                combined += (vol_shifted < vol_pct).astype(float)

        return combined


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
