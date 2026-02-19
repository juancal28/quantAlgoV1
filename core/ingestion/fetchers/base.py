"""Base fetcher interface."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FetchedArticle:
    """Normalized article returned by any news fetcher."""

    source: str
    source_url: str
    title: str
    published_at: datetime
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchedBar:
    """A single OHLCV bar returned by any market data fetcher."""

    ticker: str
    timeframe: str
    bar_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class BaseFetcher(abc.ABC):
    """Abstract base for all data fetchers."""

    @abc.abstractmethod
    async def fetch(self, **kwargs: Any) -> list[Any]:
        """Fetch data. Subclasses return lists of FetchedArticle or FetchedBar."""
