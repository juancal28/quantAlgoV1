"""Parity tests verifying C++ extension matches expected behavior."""

import math

import pytest


class TestCppCostModelParity:
    """Verify CppCostModel matches Python CostModel behavior."""

    def test_import(self):
        from _quant_core import CppCostModel
        cm = CppCostModel(1.0, 5.0, 2.0)
        assert cm.commission_per_trade == 1.0

    def test_apply_costs_buy(self):
        from _quant_core import CppCostModel
        cm = CppCostModel(1.0, 5.0, 2.0)
        # impact_bps = 5.0 + 2.0/2 = 6.0
        # fill = 100 * (1 + 6/10000) = 100.06
        assert cm.apply_costs(100.0, 10.0, "BUY") == pytest.approx(100.06)

    def test_apply_costs_sell(self):
        from _quant_core import CppCostModel
        cm = CppCostModel(1.0, 5.0, 2.0)
        assert cm.apply_costs(100.0, 10.0, "SELL") == pytest.approx(99.94)

    def test_total_cost(self):
        from _quant_core import CppCostModel
        cm = CppCostModel(1.0, 5.0, 2.0)
        total = cm.total_cost_for_trade(100.0, 10.0, "BUY")
        assert total == pytest.approx(1.6, rel=1e-6)

    def test_matches_python_wrapper(self):
        """The Python CostModel wrapper should give identical results."""
        from core.backtesting.cost_model import CostModel
        cm = CostModel(commission_per_trade=1.0, slippage_bps=5.0, spread_bps=2.0)
        assert cm.apply_costs(200.0, 50.0, "BUY") == pytest.approx(200.12)
        assert cm.apply_costs(200.0, 50.0, "SELL") == pytest.approx(199.88)
        assert cm.trade_commission() == 1.0


class TestCppPaperBrokerParity:
    """Verify CppPaperBroker matches expected behavior."""

    def test_buy_and_positions(self):
        from _quant_core import CppCostModel, CppPaperBroker
        cm = CppCostModel(0.0, 0.0, 0.0)
        broker = CppPaperBroker(100000.0, cm)

        order = broker.submit_order("AAPL", "BUY", 10.0, 150.0)
        assert order.status == "filled"
        assert broker.get_cash() == pytest.approx(98500.0)

        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].ticker == "AAPL"
        assert positions[0].quantity == pytest.approx(10.0)

    def test_sell_pnl(self):
        from _quant_core import CppCostModel, CppPaperBroker
        cm = CppCostModel(0.0, 0.0, 0.0)
        broker = CppPaperBroker(100000.0, cm)

        broker.submit_order("AAPL", "BUY", 10.0, 100.0)
        broker.submit_order("AAPL", "SELL", 10.0, 110.0)

        assert broker.realized_pnl() == pytest.approx(100.0)
        assert len(broker.get_positions()) == 0

    def test_rejected_orders(self):
        from _quant_core import CppCostModel, CppPaperBroker
        cm = CppCostModel(0.0, 0.0, 0.0)
        broker = CppPaperBroker(100.0, cm)

        # Not enough cash
        order = broker.submit_order("AAPL", "BUY", 100.0, 150.0)
        assert order.status == "rejected"

        # No position to sell
        order = broker.submit_order("AAPL", "SELL", 10.0, 150.0)
        assert order.status == "rejected"

    def test_portfolio_value(self):
        from _quant_core import CppCostModel, CppPaperBroker
        cm = CppCostModel(0.0, 0.0, 0.0)
        broker = CppPaperBroker(100000.0, cm)
        broker.submit_order("AAPL", "BUY", 10.0, 100.0)
        pv = broker.get_portfolio_value({"AAPL": 110.0})
        # cash = 99000, positions = 10 * 110 = 1100
        assert pv == pytest.approx(100100.0)


class TestCppRiskChecksParity:
    """Verify C++ risk check functions."""

    def test_circuit_breaker_not_tripped(self):
        from _quant_core import cpp_check_circuit_breaker
        result = cpp_check_circuit_breaker(
            realized_pnl=100.0, unrealized_pnl=50.0,
            peak_pnl=200.0, initial_cash=100000.0,
            max_daily_loss_pct=0.02,
        )
        assert result.tripped is False
        assert result.total_pnl == pytest.approx(150.0)

    def test_circuit_breaker_tripped(self):
        from _quant_core import cpp_check_circuit_breaker
        result = cpp_check_circuit_breaker(
            realized_pnl=-1500.0, unrealized_pnl=-600.0,
            peak_pnl=0.0, initial_cash=100000.0,
            max_daily_loss_pct=0.02,
        )
        assert result.tripped is True
        assert result.loss_pct == pytest.approx(0.021)

    def test_exposure_limit(self):
        from _quant_core import cpp_check_exposure_limit
        assert cpp_check_exposure_limit(50000.0, 100000.0, 1.0) is True
        assert cpp_check_exposure_limit(110000.0, 100000.0, 1.0) is False

    def test_trade_rate_limit(self):
        from _quant_core import cpp_check_trade_rate_limit
        assert cpp_check_trade_rate_limit(10, 30) is True
        assert cpp_check_trade_rate_limit(30, 30) is False


class TestCppPositionSizerParity:
    """Verify C++ position sizer."""

    def test_basic_sizing(self):
        from _quant_core import cpp_compute_order_quantity
        qty = cpp_compute_order_quantity(
            price=100.0, portfolio_value=100000.0,
            cash_available=50000.0, num_target_positions=5,
            max_position_pct=0.10,
        )
        # target = 100000/5 = 20000, cap at 10% = 10000, cap at cash = 10000
        assert qty == pytest.approx(100.0)

    def test_edge_cases(self):
        from _quant_core import cpp_compute_order_quantity
        assert cpp_compute_order_quantity(0.0, 100000.0, 50000.0, 5, 0.10) == 0.0
        assert cpp_compute_order_quantity(100.0, 0.0, 50000.0, 5, 0.10) == 0.0
        assert cpp_compute_order_quantity(100.0, 100000.0, 0.0, 5, 0.10) == 0.0
        assert cpp_compute_order_quantity(100.0, 100000.0, 50000.0, 0, 0.10) == 0.0


class TestCppReconcilerParity:
    """Verify C++ signal reconciler."""

    def test_reconcile(self):
        from _quant_core import cpp_reconcile_positions
        signals = {"AAPL": "long", "MSFT": "flat", "GOOGL": "long"}
        positions = {"MSFT": 10.0, "NVDA": 5.0}
        result = cpp_reconcile_positions(signals, positions)
        assert set(result.to_buy) == {"AAPL", "GOOGL"}
        assert set(result.to_sell) == {"MSFT", "NVDA"}


class TestCppMetricsParity:
    """Verify C++ metrics computation."""

    def test_empty_equity(self):
        from _quant_core import cpp_compute_metrics
        m = cpp_compute_metrics([], [])
        assert m.cagr == 0.0
        assert m.sharpe == 0.0

    def test_flat_equity(self):
        from _quant_core import cpp_compute_metrics
        equity = [100000.0] * 100
        m = cpp_compute_metrics(equity, [])
        assert m.cagr == pytest.approx(0.0, abs=1e-9)
        assert m.max_drawdown == 0.0

    def test_win_rate(self):
        from _quant_core import cpp_compute_metrics
        equity = [100.0, 101.0, 102.0]
        m = cpp_compute_metrics(equity, [0.05, -0.02, 0.03])
        assert m.win_rate == pytest.approx(2.0 / 3.0)
        assert m.avg_trade_return == pytest.approx(0.02)

    def test_thresholds(self):
        from _quant_core import CppBacktestMetrics, cpp_passes_thresholds
        m = CppBacktestMetrics()
        m.sharpe = 1.0
        m.max_drawdown = 0.15
        m.win_rate = 0.5
        assert cpp_passes_thresholds(m, 0.5, 0.25, 0.4) is True
        assert cpp_passes_thresholds(m, 1.5, 0.25, 0.4) is False


class TestCppBacktestEngineParity:
    """Verify C++ backtest engine."""

    def test_no_signals_no_trades(self):
        from _quant_core import CppBacktestEngine, CppBarData, CppCostModel
        engine = CppBacktestEngine()
        bars = [CppBarData(100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 1000, 1000000 + i * 86400)
                for i in range(10)]
        cm = CppCostModel(0.0, 0.0, 0.0)
        result = engine.run(["AAPL"], [], 5, 0.10, {"AAPL": bars}, 100000.0, cm, 0.0, 1.0, 0.0)

        assert result.equity_values[0] == pytest.approx(100000.0)
        assert len(result.equity_values) == 10
        assert len(result.trades) == 0

    def test_missing_ticker_raises(self):
        from _quant_core import CppBacktestEngine, CppCostModel
        engine = CppBacktestEngine()
        cm = CppCostModel(0.0, 0.0, 0.0)
        with pytest.raises(RuntimeError, match="No price data"):
            engine.run(["AAPL"], [], 5, 0.10, {}, 100000.0, cm, 0.0, 1.0, 0.0)


class TestPythonWrapperIntegration:
    """Verify Python wrapper modules work end-to-end via C++ backend."""

    def test_cost_model_factory(self, monkeypatch):
        """get_cost_model() should return a working CostModel with C++ backend."""
        monkeypatch.setenv("TRADING_MODE", "paper")
        monkeypatch.setenv("PAPER_GUARD", "true")
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

        import core.config as _cfg
        _cfg._settings = None

        from core.backtesting.cost_model import get_cost_model
        cm = get_cost_model()
        # Should not raise and should return valid results
        fill = cm.apply_costs(100.0, 10.0, "BUY")
        assert fill >= 100.0

        _cfg._settings = None

    def test_position_sizing_via_cpp(self, monkeypatch):
        """compute_order_quantity() should use C++ backend."""
        monkeypatch.setenv("TRADING_MODE", "paper")
        monkeypatch.setenv("PAPER_GUARD", "true")
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

        import core.config as _cfg
        _cfg._settings = None

        from core.execution.position_sizing import compute_order_quantity
        qty = compute_order_quantity("AAPL", 100.0, 100000.0, 50000.0, 5)
        assert qty > 0

        _cfg._settings = None
