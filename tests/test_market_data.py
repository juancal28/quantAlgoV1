"""Tests for market data fetching and storage."""

from __future__ import annotations

from datetime import datetime, timezone

from core.ingestion.fetchers.base import FetchedBar


def test_fetched_bar_dataclass():
    """FetchedBar can be constructed with all fields."""
    bar = FetchedBar(
        ticker="SPY",
        timeframe="1Day",
        bar_time=datetime(2025, 1, 15, 14, 30, tzinfo=timezone.utc),
        open=590.0,
        high=595.0,
        low=588.0,
        close=593.5,
        volume=40_000_000,
    )
    assert bar.ticker == "SPY"
    assert bar.close == 593.5


def test_get_market_data_fetcher_yfinance(mock_settings):
    """Factory returns YFinanceMarketDataFetcher when configured."""
    mock_settings("MARKET_DATA_PROVIDER", "yfinance")

    from core.ingestion.fetchers.market_data import (
        YFinanceMarketDataFetcher,
        get_market_data_fetcher,
    )

    fetcher = get_market_data_fetcher()
    assert isinstance(fetcher, YFinanceMarketDataFetcher)


def test_get_market_data_fetcher_alpaca(mock_settings):
    """Factory returns AlpacaMarketDataFetcher when configured."""
    mock_settings("MARKET_DATA_PROVIDER", "alpaca")

    from core.ingestion.fetchers.market_data import (
        AlpacaMarketDataFetcher,
        get_market_data_fetcher,
    )

    fetcher = get_market_data_fetcher()
    assert isinstance(fetcher, AlpacaMarketDataFetcher)


def test_get_market_data_fetcher_invalid(mock_settings):
    """Factory raises for unknown provider."""
    mock_settings("MARKET_DATA_PROVIDER", "bogus")

    import pytest

    from core.ingestion.fetchers.market_data import get_market_data_fetcher

    with pytest.raises(ValueError, match="Unknown MARKET_DATA_PROVIDER"):
        get_market_data_fetcher()
