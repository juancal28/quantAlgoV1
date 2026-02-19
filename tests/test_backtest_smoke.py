"""Smoke tests for the backtest engine, cost model, and metrics.

Uses synthetic price data only — no DB, no external calls.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from core.backtesting.cost_model import CostModel, get_cost_model
from core.backtesting.engine import BacktestResult, BuiltinEngine, Trade, run_backtest
from core.backtesting.metrics import BacktestMetrics, compute_metrics, passes_thresholds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_price_df(
    start: datetime | None = None,
    num_bars: int = 252,
    start_price: float = 100.0,
    daily_return: float = 0.0005,
    volatility: float = 0.01,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a deterministic synthetic price DataFrame.

    Returns a DataFrame with columns: open, high, low, close, volume
    indexed by datetime.
    """
    rng = np.random.RandomState(seed)
    if start is None:
        start = datetime(2023, 1, 3)

    dates = [start + timedelta(days=i) for i in range(num_bars)]
    log_returns = rng.normal(daily_return, volatility, num_bars)
    prices = start_price * np.exp(np.cumsum(log_returns))

    # Build OHLCV from synthetic close prices
    opens = prices
    highs = prices * (1 + rng.uniform(0, 0.02, num_bars))
    lows = prices * (1 - rng.uniform(0, 0.02, num_bars))
    closes = prices * (1 + rng.normal(0, 0.005, num_bars))
    volumes = rng.randint(100_000, 1_000_000, num_bars)

    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        },
        index=dates,
    )


ZERO_COST = CostModel(commission_per_trade=0.0, slippage_bps=0.0, spread_bps=0.0)
DEFAULT_COST = CostModel(commission_per_trade=1.0, slippage_bps=5.0, spread_bps=2.0)

SIMPLE_DEFINITION = {
    "name": "test_strat",
    "universe": ["SPY"],
    "signals": [
        {"type": "news_sentiment", "lookback_minutes": 240, "threshold": 0.65, "direction": "long"},
    ],
    "rules": {
        "rebalance_minutes": 60,
        "max_positions": 5,
        "position_sizing": {"type": "equal_weight", "max_position_pct": 0.10},
        "exits": [],
    },
}


# ===========================================================================
# TestCostModel
# ===========================================================================


class TestCostModel:
    def test_buy_increases_fill_price(self):
        cm = DEFAULT_COST
        fill = cm.apply_costs(100.0, 10, "BUY")
        assert fill > 100.0

    def test_sell_decreases_fill_price(self):
        cm = DEFAULT_COST
        fill = cm.apply_costs(100.0, 10, "SELL")
        assert fill < 100.0

    def test_zero_cost_no_impact(self):
        fill_buy = ZERO_COST.apply_costs(100.0, 10, "BUY")
        fill_sell = ZERO_COST.apply_costs(100.0, 10, "SELL")
        assert fill_buy == 100.0
        assert fill_sell == 100.0

    def test_commission_included_in_total(self):
        cm = CostModel(commission_per_trade=5.0, slippage_bps=0.0, spread_bps=0.0)
        total = cm.total_cost_for_trade(100.0, 10, "BUY")
        assert total == 5.0  # zero impact + 5.0 commission

    def test_factory_reads_config(self):
        cm = get_cost_model()
        assert cm.commission_per_trade == 1.0
        assert cm.slippage_bps == 5.0
        assert cm.spread_bps == 2.0


# ===========================================================================
# TestMetrics
# ===========================================================================


class TestMetrics:
    def test_all_fields_present(self):
        eq = pd.Series([100, 101, 102, 103], dtype=float)
        m = compute_metrics(eq, [0.01, 0.02])
        assert isinstance(m, BacktestMetrics)
        for attr in ("cagr", "sharpe", "max_drawdown", "win_rate", "turnover", "avg_trade_return"):
            assert hasattr(m, attr)
            assert isinstance(getattr(m, attr), float)

    def test_positive_equity_positive_cagr(self):
        # Steadily rising equity
        eq = pd.Series(np.linspace(100, 150, 252), dtype=float)
        m = compute_metrics(eq, [0.01])
        assert m.cagr > 0

    def test_declining_equity_negative_cagr(self):
        eq = pd.Series(np.linspace(100, 80, 252), dtype=float)
        m = compute_metrics(eq, [-0.01])
        assert m.cagr < 0

    def test_max_drawdown_computed(self):
        # Equity goes up then drops
        values = list(range(100, 120)) + list(range(120, 100, -1))
        eq = pd.Series(values, dtype=float)
        m = compute_metrics(eq, [])
        assert m.max_drawdown > 0

    def test_win_rate_calculation(self):
        eq = pd.Series([100, 101, 102], dtype=float)
        returns = [0.05, -0.02, 0.03, 0.01]  # 3 wins, 1 loss
        m = compute_metrics(eq, returns)
        assert m.win_rate == pytest.approx(0.75)

    def test_empty_equity_returns_zeros(self):
        eq = pd.Series([], dtype=float)
        m = compute_metrics(eq, [])
        assert m.cagr == 0.0
        assert m.sharpe == 0.0
        assert m.max_drawdown == 0.0

    def test_single_bar_returns_zeros(self):
        eq = pd.Series([100.0], dtype=float)
        m = compute_metrics(eq, [])
        assert m.cagr == 0.0
        assert m.sharpe == 0.0

    def test_passes_thresholds_good(self):
        m = BacktestMetrics(
            cagr=0.15, sharpe=1.5, max_drawdown=0.10,
            win_rate=0.60, turnover=0.01, avg_trade_return=0.005,
        )
        assert passes_thresholds(m) is True

    def test_passes_thresholds_bad_sharpe(self):
        m = BacktestMetrics(
            cagr=0.15, sharpe=0.2, max_drawdown=0.10,
            win_rate=0.60, turnover=0.01, avg_trade_return=0.005,
        )
        assert passes_thresholds(m) is False

    def test_passes_thresholds_bad_drawdown(self):
        m = BacktestMetrics(
            cagr=0.15, sharpe=1.5, max_drawdown=0.30,
            win_rate=0.60, turnover=0.01, avg_trade_return=0.005,
        )
        assert passes_thresholds(m) is False

    def test_passes_thresholds_bad_win_rate(self):
        m = BacktestMetrics(
            cagr=0.15, sharpe=1.5, max_drawdown=0.10,
            win_rate=0.30, turnover=0.01, avg_trade_return=0.005,
        )
        assert passes_thresholds(m) is False


# ===========================================================================
# TestBuiltinEngine
# ===========================================================================


class TestBuiltinEngine:
    def test_smoke_returns_backtest_result(self):
        price_data = {"SPY": _make_price_df(num_bars=300)}
        result = run_backtest(SIMPLE_DEFINITION, price_data, cost_model=ZERO_COST)
        assert isinstance(result, BacktestResult)
        assert isinstance(result.metrics, BacktestMetrics)
        assert isinstance(result.passed, bool)

    def test_equity_curve_starts_at_initial_cash(self):
        price_data = {"SPY": _make_price_df(num_bars=300)}
        result = run_backtest(
            SIMPLE_DEFINITION, price_data, initial_cash=50_000, cost_model=ZERO_COST,
        )
        assert result.equity_curve.iloc[0] == pytest.approx(50_000)

    def test_missing_ticker_raises(self):
        # Definition references SPY but we provide QQQ
        price_data = {"QQQ": _make_price_df(num_bars=300)}
        with pytest.raises(ValueError, match="No price data for ticker"):
            run_backtest(SIMPLE_DEFINITION, price_data, cost_model=ZERO_COST)

    def test_insufficient_data_raises(self):
        price_data = {"SPY": _make_price_df(num_bars=1)}
        with pytest.raises(ValueError, match="Insufficient data"):
            run_backtest(SIMPLE_DEFINITION, price_data, cost_model=ZERO_COST)

    def test_volatility_filter_signal(self):
        defn = {
            "name": "vol_test",
            "universe": ["SPY"],
            "signals": [
                {"type": "volatility_filter", "max_vix": 25},
            ],
            "rules": {
                "rebalance_minutes": 60,
                "max_positions": 5,
                "position_sizing": {"type": "equal_weight", "max_position_pct": 0.10},
                "exits": [],
            },
        }
        price_data = {"SPY": _make_price_df(num_bars=300, volatility=0.005)}
        result = run_backtest(defn, price_data, cost_model=ZERO_COST)
        assert isinstance(result, BacktestResult)

    def test_zero_cost_model_no_drag(self):
        price_data = {"SPY": _make_price_df(num_bars=300, daily_return=0.001, seed=99)}
        result_zero = run_backtest(SIMPLE_DEFINITION, price_data, cost_model=ZERO_COST)
        result_cost = run_backtest(SIMPLE_DEFINITION, price_data, cost_model=DEFAULT_COST)
        # With costs, final equity should be <= zero-cost equity
        assert result_zero.equity_curve.iloc[-1] >= result_cost.equity_curve.iloc[-1]

    def test_trades_have_required_attributes(self):
        price_data = {"SPY": _make_price_df(num_bars=300)}
        result = run_backtest(SIMPLE_DEFINITION, price_data, cost_model=DEFAULT_COST)
        if result.trades:
            t = result.trades[0]
            assert hasattr(t, "ticker")
            assert hasattr(t, "side")
            assert hasattr(t, "quantity")
            assert hasattr(t, "price")
            assert hasattr(t, "bar_time")
            assert hasattr(t, "pnl")

    def test_multi_ticker_universe(self):
        defn = {
            "name": "multi",
            "universe": ["SPY", "QQQ"],
            "signals": [
                {"type": "volatility_filter", "max_vix": 30},
            ],
            "rules": {
                "rebalance_minutes": 60,
                "max_positions": 5,
                "position_sizing": {"type": "equal_weight", "max_position_pct": 0.10},
                "exits": [],
            },
        }
        price_data = {
            "SPY": _make_price_df(num_bars=300, seed=1),
            "QQQ": _make_price_df(num_bars=300, seed=2),
        }
        result = run_backtest(defn, price_data, cost_model=ZERO_COST)
        assert isinstance(result, BacktestResult)
        assert len(result.equity_curve) == 300
