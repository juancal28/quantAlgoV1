"""Tests for AlpacaPaperBroker and get_broker() factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestAlpacaPaperBrokerConstruction:
    """Construction and guard enforcement."""

    def test_construction_enforces_guard(self, mock_settings):
        """AlpacaPaperBroker raises when PAPER_GUARD=false."""
        mock_settings("TRADING_MODE", "paper")
        mock_settings("PAPER_GUARD", "false")

        from core.execution.alpaca_paper import AlpacaPaperBroker

        with pytest.raises(RuntimeError, match="PAPER_GUARD"):
            AlpacaPaperBroker()


class TestAlpacaPaperBrokerMethods:
    """Tests with mocked TradingClient."""

    @pytest.fixture(autouse=True)
    def _setup(self, mock_settings):
        mock_settings("TRADING_MODE", "paper")
        mock_settings("PAPER_GUARD", "true")
        mock_settings("ALPACA_API_KEY", "test-key")
        mock_settings("ALPACA_API_SECRET", "test-secret")

    @patch("core.execution.alpaca_paper.TradingClient")
    def test_submit_order_calls_alpaca(self, mock_tc_cls):
        from core.execution.alpaca_paper import AlpacaPaperBroker

        mock_client = MagicMock()
        mock_tc_cls.return_value = mock_client

        mock_alpaca_order = MagicMock()
        mock_alpaca_order.id = "order-123"
        mock_alpaca_order.filled_avg_price = "150.50"
        mock_alpaca_order.filled_qty = "10"
        mock_client.submit_order.return_value = mock_alpaca_order

        broker = AlpacaPaperBroker()
        order = broker.submit_order("AAPL", "BUY", 10, 150.0)

        mock_client.submit_order.assert_called_once()
        assert order.ticker == "AAPL"
        assert order.side == "BUY"
        assert order.quantity == 10
        assert order.price == 150.50
        assert order.order_id == "order-123"
        assert order.status == "filled"

    @patch("core.execution.alpaca_paper.TradingClient")
    def test_get_positions_maps_correctly(self, mock_tc_cls):
        from core.execution.alpaca_paper import AlpacaPaperBroker

        mock_client = MagicMock()
        mock_tc_cls.return_value = mock_client

        mock_pos = MagicMock()
        mock_pos.symbol = "SPY"
        mock_pos.qty = "50"
        mock_pos.avg_entry_price = "450.00"
        mock_pos.market_value = "23000.00"
        mock_pos.unrealized_pl = "500.00"
        mock_client.get_all_positions.return_value = [mock_pos]

        broker = AlpacaPaperBroker()
        positions = broker.get_positions()

        assert len(positions) == 1
        assert positions[0].ticker == "SPY"
        assert positions[0].quantity == 50.0
        assert positions[0].avg_entry_price == 450.0
        assert positions[0].market_value == 23000.0
        assert positions[0].unrealized_pnl == 500.0

    @patch("core.execution.alpaca_paper.TradingClient")
    def test_get_cash_from_account(self, mock_tc_cls):
        from core.execution.alpaca_paper import AlpacaPaperBroker

        mock_client = MagicMock()
        mock_tc_cls.return_value = mock_client

        mock_account = MagicMock()
        mock_account.cash = "75000.50"
        mock_client.get_account.return_value = mock_account

        broker = AlpacaPaperBroker()
        assert broker.get_cash() == 75000.50

    @patch("core.execution.alpaca_paper.TradingClient")
    def test_get_portfolio_value_from_account(self, mock_tc_cls):
        from core.execution.alpaca_paper import AlpacaPaperBroker

        mock_client = MagicMock()
        mock_tc_cls.return_value = mock_client

        mock_account = MagicMock()
        mock_account.equity = "125000.00"
        mock_client.get_account.return_value = mock_account

        broker = AlpacaPaperBroker()
        value = broker.get_portfolio_value({})
        assert value == 125000.0

    @patch("core.execution.alpaca_paper.TradingClient")
    def test_unrealized_pnl_from_positions(self, mock_tc_cls):
        from core.execution.alpaca_paper import AlpacaPaperBroker

        mock_client = MagicMock()
        mock_tc_cls.return_value = mock_client

        pos1 = MagicMock()
        pos1.unrealized_pl = "200.00"
        pos2 = MagicMock()
        pos2.unrealized_pl = "-50.00"
        mock_client.get_all_positions.return_value = [pos1, pos2]

        broker = AlpacaPaperBroker()
        assert broker.unrealized_pnl({}) == 150.0

    @patch("core.execution.alpaca_paper.TradingClient")
    def test_gross_exposure_from_positions(self, mock_tc_cls):
        from core.execution.alpaca_paper import AlpacaPaperBroker

        mock_client = MagicMock()
        mock_tc_cls.return_value = mock_client

        pos1 = MagicMock()
        pos1.market_value = "10000.00"
        pos2 = MagicMock()
        pos2.market_value = "-5000.00"
        mock_client.get_all_positions.return_value = [pos1, pos2]

        broker = AlpacaPaperBroker()
        assert broker.gross_exposure({}) == 15000.0

    @patch("core.execution.alpaca_paper.TradingClient")
    def test_realized_pnl_tracks_sells(self, mock_tc_cls):
        from core.execution.alpaca_paper import AlpacaPaperBroker

        mock_client = MagicMock()
        mock_tc_cls.return_value = mock_client

        # Buy order
        buy_order = MagicMock()
        buy_order.id = "buy-1"
        buy_order.filled_avg_price = "100.00"
        buy_order.filled_qty = "10"

        # Sell order at higher price
        sell_order = MagicMock()
        sell_order.id = "sell-1"
        sell_order.filled_avg_price = "110.00"
        sell_order.filled_qty = "10"

        mock_client.submit_order.side_effect = [buy_order, sell_order]

        broker = AlpacaPaperBroker()
        broker.submit_order("AAPL", "BUY", 10, 100.0)
        broker.submit_order("AAPL", "SELL", 10, 110.0)

        # Realized PnL: (110 - 100) * 10 = 100
        assert broker.realized_pnl == 100.0


class TestGetBrokerFactory:
    """Tests for get_broker() factory function."""

    def test_get_broker_factory_internal(self, mock_settings):
        """Factory returns PaperBroker by default."""
        mock_settings("TRADING_MODE", "paper")
        mock_settings("PAPER_GUARD", "true")
        mock_settings("BROKER_PROVIDER", "internal")

        from core.execution.alpaca_paper import get_broker
        from core.execution.paper_broker import PaperBroker

        broker = get_broker()
        assert isinstance(broker, PaperBroker)

    @patch("core.execution.alpaca_paper.TradingClient")
    def test_get_broker_factory_alpaca(self, mock_tc_cls, mock_settings):
        """Factory returns AlpacaPaperBroker when configured."""
        mock_settings("TRADING_MODE", "paper")
        mock_settings("PAPER_GUARD", "true")
        mock_settings("BROKER_PROVIDER", "alpaca")
        mock_settings("ALPACA_API_KEY", "test-key")
        mock_settings("ALPACA_API_SECRET", "test-secret")

        from core.execution.alpaca_paper import AlpacaPaperBroker, get_broker

        broker = get_broker()
        assert isinstance(broker, AlpacaPaperBroker)
