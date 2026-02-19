"""Market data fetcher (Alpaca / yfinance).

Fetches OHLCV bars for tickers in the approved universe and persists them
to the market_bars table via market_data_repo.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from core.config import get_settings
from core.ingestion.fetchers.base import BaseFetcher, FetchedBar
from core.logging import get_logger

logger = get_logger(__name__)


class AlpacaMarketDataFetcher(BaseFetcher):
    """Fetches historical bars from the Alpaca Data API."""

    async def fetch(
        self,
        tickers: list[str] | None = None,
        lookback_days: int | None = None,
        timeframe: str | None = None,
        **kwargs: Any,
    ) -> list[FetchedBar]:
        settings = get_settings()
        tickers = tickers or settings.approved_universe_list
        lookback_days = lookback_days or settings.MARKET_DATA_LOOKBACK_DAYS
        timeframe = timeframe or settings.BAR_TIMEFRAME

        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        tf_map = {
            "1Day": TimeFrame.Day,
            "1Hour": TimeFrame.Hour,
            "1Min": TimeFrame.Minute,
        }
        alpaca_tf = tf_map.get(timeframe, TimeFrame.Day)

        client = StockHistoricalDataClient(
            api_key=settings.ALPACA_API_KEY or None,
            secret_key=settings.ALPACA_API_SECRET or None,
        )

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days)

        request = StockBarsRequest(
            symbol_or_symbols=tickers,
            timeframe=alpaca_tf,
            start=start,
            end=end,
        )

        logger.info(
            "Fetching Alpaca bars",
            extra={"tickers": tickers, "start": str(start), "end": str(end)},
        )

        barset = client.get_stock_bars(request)
        bars: list[FetchedBar] = []

        for symbol, symbol_bars in barset.data.items():
            for bar in symbol_bars:
                bars.append(
                    FetchedBar(
                        ticker=symbol,
                        timeframe=timeframe,
                        bar_time=bar.timestamp,
                        open=float(bar.open),
                        high=float(bar.high),
                        low=float(bar.low),
                        close=float(bar.close),
                        volume=int(bar.volume),
                    )
                )

        logger.info("Fetched %d bars from Alpaca", len(bars))
        return bars


class YFinanceMarketDataFetcher(BaseFetcher):
    """Fetches historical bars from Yahoo Finance via yfinance."""

    async def fetch(
        self,
        tickers: list[str] | None = None,
        lookback_days: int | None = None,
        timeframe: str | None = None,
        **kwargs: Any,
    ) -> list[FetchedBar]:
        import yfinance as yf

        settings = get_settings()
        tickers = tickers or settings.approved_universe_list
        lookback_days = lookback_days or settings.MARKET_DATA_LOOKBACK_DAYS
        timeframe = timeframe or settings.BAR_TIMEFRAME

        tf_map = {"1Day": "1d", "1Hour": "1h", "1Min": "1m"}
        yf_interval = tf_map.get(timeframe, "1d")

        period = f"{lookback_days}d"
        # yfinance caps period for intraday data
        if yf_interval in ("1m",):
            period = "7d"
        elif yf_interval in ("1h",):
            period = "730d"

        logger.info(
            "Fetching yfinance bars",
            extra={"tickers": tickers, "period": period, "interval": yf_interval},
        )

        bars: list[FetchedBar] = []

        for ticker in tickers:
            try:
                tk = yf.Ticker(ticker)
                df = tk.history(period=period, interval=yf_interval)

                if df.empty:
                    logger.warning("No data returned for %s", ticker)
                    continue

                for idx, row in df.iterrows():
                    bar_time = idx.to_pydatetime()
                    if bar_time.tzinfo is None:
                        bar_time = bar_time.replace(tzinfo=timezone.utc)

                    bars.append(
                        FetchedBar(
                            ticker=ticker,
                            timeframe=timeframe,
                            bar_time=bar_time,
                            open=float(row["Open"]),
                            high=float(row["High"]),
                            low=float(row["Low"]),
                            close=float(row["Close"]),
                            volume=int(row["Volume"]),
                        )
                    )
            except Exception:
                logger.exception("Failed to fetch data for %s", ticker)

        logger.info("Fetched %d bars from yfinance", len(bars))
        return bars


def get_market_data_fetcher() -> BaseFetcher:
    """Factory: returns the configured market data fetcher."""
    provider = get_settings().MARKET_DATA_PROVIDER.lower()
    if provider == "alpaca":
        return AlpacaMarketDataFetcher()
    elif provider == "yfinance":
        return YFinanceMarketDataFetcher()
    else:
        raise ValueError(f"Unknown MARKET_DATA_PROVIDER: {provider!r}")


async def fetch_and_store_bars(
    session: Any,
    tickers: list[str] | None = None,
    lookback_days: int | None = None,
) -> int:
    """High-level: fetch bars from the configured provider and upsert to DB.

    Returns the number of rows upserted.
    """
    from core.storage.models import MarketBar
    from core.storage.repos import market_data_repo

    fetcher = get_market_data_fetcher()
    fetched = await fetcher.fetch(tickers=tickers, lookback_days=lookback_days)

    if not fetched:
        logger.warning("No bars fetched")
        return 0

    models = [
        MarketBar(
            id=uuid.uuid4(),
            ticker=b.ticker,
            timeframe=b.timeframe,
            bar_time=b.bar_time,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
            fetched_at=datetime.now(timezone.utc),
        )
        for b in fetched
    ]

    count = await market_data_repo.upsert_bars(session, models)
    await session.commit()
    logger.info("Upserted %d bars to database", count)
    return count
