"""Real-time price fetching abstraction."""

from __future__ import annotations

import abc
from datetime import datetime, timedelta, timezone

from core.logging import get_logger

logger = get_logger(__name__)


class PriceFeed(abc.ABC):
    """Abstract base for fetching current prices."""

    @abc.abstractmethod
    def get_prices(self, tickers: list[str]) -> dict[str, float]:
        """Return {ticker: price} for the requested tickers.

        Tickers with stale or unavailable data are omitted from the result.
        """
        ...


class AlpacaPriceFeed(PriceFeed):
    """Fetch latest bar open prices from Alpaca Data API.

    Uses bar.open as the signal price (# lookahead guard: shift(1)).
    Skips tickers whose latest bar is older than RISK_MAX_DATA_STALENESS_MINUTES.
    """

    def __init__(self) -> None:
        from alpaca.data.historical import StockHistoricalDataClient

        from core.config import get_settings

        s = get_settings()
        self._client = StockHistoricalDataClient(
            api_key=s.ALPACA_API_KEY,
            secret_key=s.ALPACA_API_SECRET,
        )
        self._staleness_minutes = s.RISK_MAX_DATA_STALENESS_MINUTES

    def get_prices(self, tickers: list[str]) -> dict[str, float]:
        from alpaca.data.requests import StockLatestBarRequest

        if not tickers:
            return {}

        req = StockLatestBarRequest(symbol_or_symbols=tickers)
        bars = self._client.get_stock_latest_bar(req)

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=self._staleness_minutes)
        prices: dict[str, float] = {}

        for ticker, bar in bars.items():
            bar_time = bar.timestamp
            if bar_time.tzinfo is None:
                bar_time = bar_time.replace(tzinfo=timezone.utc)
            if bar_time < cutoff:
                logger.warning(
                    "Skipping stale data for %s: bar_time=%s (cutoff=%s)",
                    ticker, bar_time, cutoff,
                )
                continue
            # lookahead guard: shift(1) — use open price, not close
            prices[ticker] = float(bar.open)

        return prices


class DbPriceFeed(PriceFeed):
    """Fetch latest bar open prices from Postgres via market_data_repo.

    Used when BROKER_PROVIDER=internal (no Alpaca data connection).
    """

    def __init__(self, session) -> None:
        self._session = session
        from core.config import get_settings

        self._staleness_minutes = get_settings().RISK_MAX_DATA_STALENESS_MINUTES

    def get_prices(self, tickers: list[str]) -> dict[str, float]:
        import asyncio

        return asyncio.get_event_loop().run_until_complete(
            self._get_prices_async(tickers)
        )

    async def _get_prices_async(self, tickers: list[str]) -> dict[str, float]:
        from core.storage.repos import market_data_repo

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=self._staleness_minutes)
        prices: dict[str, float] = {}

        for ticker in tickers:
            bars = await market_data_repo.get_bars_for_ticker(
                self._session, ticker, limit=1
            )
            if not bars:
                logger.warning("No bars found for %s in DB", ticker)
                continue
            bar = bars[0]
            bar_time = bar.bar_time
            if bar_time.tzinfo is None:
                bar_time = bar_time.replace(tzinfo=timezone.utc)
            if bar_time < cutoff:
                logger.warning(
                    "Skipping stale DB data for %s: bar_time=%s (cutoff=%s)",
                    ticker, bar_time, cutoff,
                )
                continue
            # lookahead guard: shift(1) — use open price, not close
            prices[ticker] = float(bar.open)

        return prices


class MockPriceFeed(PriceFeed):
    """Return preset prices. For tests."""

    def __init__(self, prices: dict[str, float]) -> None:
        self._prices = dict(prices)

    def get_prices(self, tickers: list[str]) -> dict[str, float]:
        return {t: self._prices[t] for t in tickers if t in self._prices}


def get_price_feed(session=None) -> PriceFeed:
    """Factory: return the configured price feed.

    - BROKER_PROVIDER=alpaca -> AlpacaPriceFeed
    - Otherwise -> DbPriceFeed(session)
    """
    from core.config import get_settings

    provider = get_settings().BROKER_PROVIDER.lower()
    if provider == "alpaca":
        return AlpacaPriceFeed()
    return DbPriceFeed(session)
