"""Tests for PAPER_GUARD enforcement."""

from __future__ import annotations

import pytest

from core.config import _reset_settings


class TestEnsurePaperMode:
    """Tests for ensure_paper_mode()."""

    def test_passes_in_paper_mode(self, mock_settings):
        """Guard passes when TRADING_MODE=paper and PAPER_GUARD=true."""
        mock_settings("TRADING_MODE", "paper")
        mock_settings("PAPER_GUARD", "true")

        from core.execution.guard import ensure_paper_mode

        ensure_paper_mode()  # Should not raise

    def test_raises_when_trading_mode_live(self, monkeypatch):
        """Guard raises RuntimeError when TRADING_MODE=live."""
        from unittest.mock import MagicMock

        from core.execution.guard import ensure_paper_mode

        # Monkeypatch get_settings at the source module to return fake settings
        # (bypass the sys.exit in get_settings itself)
        fake_settings = MagicMock()
        fake_settings.TRADING_MODE = "live"
        fake_settings.PAPER_GUARD = True
        monkeypatch.setattr("core.config.get_settings", lambda: fake_settings)

        with pytest.raises(RuntimeError, match="not 'paper'"):
            ensure_paper_mode()

    def test_raises_when_paper_guard_false(self, mock_settings):
        """Guard raises RuntimeError when PAPER_GUARD=false."""
        mock_settings("TRADING_MODE", "paper")
        mock_settings("PAPER_GUARD", "false")

        from core.execution.guard import ensure_paper_mode

        with pytest.raises(RuntimeError, match="PAPER_GUARD is disabled"):
            ensure_paper_mode()


class TestPaperBrokerGuard:
    """Tests for PaperBroker guard enforcement."""

    def test_construction_succeeds_in_paper_mode(self, mock_settings):
        """PaperBroker can be constructed in paper mode."""
        mock_settings("TRADING_MODE", "paper")
        mock_settings("PAPER_GUARD", "true")

        from core.execution.paper_broker import PaperBroker

        broker = PaperBroker()
        assert broker.get_cash() > 0

    def test_construction_raises_when_guard_false(self, mock_settings):
        """PaperBroker construction raises when PAPER_GUARD=false."""
        mock_settings("TRADING_MODE", "paper")
        mock_settings("PAPER_GUARD", "false")

        from core.execution.paper_broker import PaperBroker

        with pytest.raises(RuntimeError, match="PAPER_GUARD"):
            PaperBroker()

    def test_submit_order_rechecks_guard(self, mock_settings, monkeypatch):
        """PaperBroker.submit_order() re-checks the guard on each call."""
        mock_settings("TRADING_MODE", "paper")
        mock_settings("PAPER_GUARD", "true")

        from core.execution.paper_broker import PaperBroker

        broker = PaperBroker()

        # Now disable the guard mid-session
        mock_settings("PAPER_GUARD", "false")

        with pytest.raises(RuntimeError, match="PAPER_GUARD"):
            broker.submit_order("SPY", "BUY", 10, 100.0)


class TestAlpacaPaperBrokerGuard:
    """Tests for AlpacaPaperBroker guard enforcement."""

    def test_construction_enforces_guard(self, mock_settings):
        """AlpacaPaperBroker raises when PAPER_GUARD=false."""
        mock_settings("TRADING_MODE", "paper")
        mock_settings("PAPER_GUARD", "false")

        from core.execution.alpaca_paper import AlpacaPaperBroker

        with pytest.raises(RuntimeError, match="PAPER_GUARD"):
            AlpacaPaperBroker()
