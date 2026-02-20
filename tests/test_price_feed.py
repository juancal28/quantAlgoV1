"""Tests for price feed abstraction."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.execution.price_feed import DbPriceFeed, MockPriceFeed
from core.storage.models import MarketBar


class TestMockPriceFeed:
    """Tests for MockPriceFeed."""

    def test_returns_preset_prices(self):
        feed = MockPriceFeed({"SPY": 450.0, "QQQ": 380.0})
        prices = feed.get_prices(["SPY", "QQQ"])
        assert prices == {"SPY": 450.0, "QQQ": 380.0}

    def test_omits_unknown_tickers(self):
        feed = MockPriceFeed({"SPY": 450.0})
        prices = feed.get_prices(["SPY", "AAPL"])
        assert prices == {"SPY": 450.0}
        assert "AAPL" not in prices

    def test_empty_request(self):
        feed = MockPriceFeed({"SPY": 450.0})
        prices = feed.get_prices([])
        assert prices == {}

    def test_empty_preset(self):
        feed = MockPriceFeed({})
        prices = feed.get_prices(["SPY"])
        assert prices == {}


@pytest.mark.asyncio
class TestDbPriceFeed:
    """Tests for DbPriceFeed."""

    async def test_returns_open_price(self, db_session, mock_settings):
        """DbPriceFeed should return the bar's open price (lookahead guard)."""
        mock_settings("RISK_MAX_DATA_STALENESS_MINUTES", "60")

        bar = MarketBar(
            id=uuid.uuid4(),
            ticker="SPY",
            timeframe="1Day",
            bar_time=datetime.now(timezone.utc) - timedelta(minutes=10),
            open=449.50,
            high=452.00,
            low=448.00,
            close=451.00,
            volume=50000000,
            fetched_at=datetime.now(timezone.utc),
        )
        db_session.add(bar)
        await db_session.flush()

        feed = DbPriceFeed(db_session)
        prices = await feed._get_prices_async(["SPY"])
        assert "SPY" in prices
        assert prices["SPY"] == 449.50  # open, not close

    async def test_skips_stale_data(self, db_session, mock_settings):
        """DbPriceFeed should skip bars older than staleness threshold."""
        mock_settings("RISK_MAX_DATA_STALENESS_MINUTES", "30")

        bar = MarketBar(
            id=uuid.uuid4(),
            ticker="SPY",
            timeframe="1Day",
            bar_time=datetime.now(timezone.utc) - timedelta(minutes=60),
            open=449.50,
            high=452.00,
            low=448.00,
            close=451.00,
            volume=50000000,
            fetched_at=datetime.now(timezone.utc) - timedelta(minutes=60),
        )
        db_session.add(bar)
        await db_session.flush()

        feed = DbPriceFeed(db_session)
        prices = await feed._get_prices_async(["SPY"])
        assert prices == {}  # skipped due to staleness

    async def test_empty_bars(self, db_session, mock_settings):
        """DbPriceFeed should return empty dict when no bars exist."""
        mock_settings("RISK_MAX_DATA_STALENESS_MINUTES", "60")

        feed = DbPriceFeed(db_session)
        prices = await feed._get_prices_async(["SPY"])
        assert prices == {}

    async def test_multiple_tickers(self, db_session, mock_settings):
        """DbPriceFeed returns prices for multiple tickers."""
        mock_settings("RISK_MAX_DATA_STALENESS_MINUTES", "60")

        now = datetime.now(timezone.utc)
        for ticker, open_price in [("SPY", 450.0), ("QQQ", 380.0)]:
            bar = MarketBar(
                id=uuid.uuid4(),
                ticker=ticker,
                timeframe="1Day",
                bar_time=now - timedelta(minutes=5),
                open=open_price,
                high=open_price + 2,
                low=open_price - 2,
                close=open_price + 1,
                volume=10000000,
                fetched_at=now,
            )
            db_session.add(bar)
        await db_session.flush()

        feed = DbPriceFeed(db_session)
        prices = await feed._get_prices_async(["SPY", "QQQ"])
        assert prices == {"SPY": 450.0, "QQQ": 380.0}
