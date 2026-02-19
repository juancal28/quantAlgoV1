"""Repository functions for market_bars table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.storage.models import MarketBar


async def upsert_bars(session: AsyncSession, bars: list[MarketBar]) -> int:
    """Upsert market bars (insert or skip on conflict). Returns count of rows affected."""
    if not bars:
        return 0

    values = [
        {
            "id": b.id,
            "ticker": b.ticker,
            "timeframe": b.timeframe,
            "bar_time": b.bar_time,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
            "fetched_at": b.fetched_at,
        }
        for b in bars
    ]

    stmt = pg_insert(MarketBar).values(values)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["ticker", "timeframe", "bar_time"]
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount  # type: ignore[return-value]


async def get_bars_for_ticker(
    session: AsyncSession,
    ticker: str,
    timeframe: str = "1Day",
    limit: int = 365,
) -> list[MarketBar]:
    """Return bars for a ticker ordered by bar_time descending."""
    stmt = (
        select(MarketBar)
        .where(MarketBar.ticker == ticker, MarketBar.timeframe == timeframe)
        .order_by(MarketBar.bar_time.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_bars_in_range(
    session: AsyncSession,
    ticker: str,
    start: datetime,
    end: datetime,
    timeframe: str = "1Day",
) -> list[MarketBar]:
    """Return bars for a ticker within a date range, ordered chronologically."""
    stmt = (
        select(MarketBar)
        .where(
            MarketBar.ticker == ticker,
            MarketBar.timeframe == timeframe,
            MarketBar.bar_time >= start,
            MarketBar.bar_time <= end,
        )
        .order_by(MarketBar.bar_time.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
