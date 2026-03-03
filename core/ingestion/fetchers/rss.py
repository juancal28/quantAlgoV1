"""RSS feed fetcher."""

from __future__ import annotations

from datetime import datetime, timezone
from time import mktime
from typing import Any

import feedparser
import httpx

from core.config import get_settings
from core.ingestion.fetchers.base import BaseFetcher, FetchedArticle
from core.ingestion.normalize import normalize_content
from core.logging import get_logger

logger = get_logger(__name__)


def _parse_published(entry: Any) -> datetime:
    """Extract published datetime from a feedparser entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
    return datetime.now(timezone.utc)


def _extract_content(entry: Any) -> str:
    """Extract the best available content from a feedparser entry."""
    # Try content field first (full article)
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].get("value", "")
    # Fall back to summary/description
    if hasattr(entry, "summary") and entry.summary:
        return entry.summary
    if hasattr(entry, "description") and entry.description:
        return entry.description
    return ""


class RSSFetcher(BaseFetcher):
    """Fetches articles from RSS feeds."""

    async def fetch(
        self,
        feed_urls: list[str] | None = None,
        max_items: int | None = None,
        **kwargs: Any,
    ) -> list[FetchedArticle]:
        settings = get_settings()
        max_items = max_items or settings.MAX_DOCS_PER_POLL

        if feed_urls is None:
            feed_urls = self._parse_feed_urls(settings.NEWS_SOURCES)

        articles: list[FetchedArticle] = []

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for url in feed_urls:
                try:
                    fetched = await self._fetch_feed(client, url, max_items - len(articles))
                    articles.extend(fetched)
                    if len(articles) >= max_items:
                        break
                except Exception:
                    logger.exception("Failed to fetch RSS feed: %s", url)

        return articles[:max_items]

    async def _fetch_feed(
        self,
        client: httpx.AsyncClient,
        feed_url: str,
        remaining: int,
    ) -> list[FetchedArticle]:
        """Fetch and parse a single RSS feed."""
        resp = await client.get(feed_url)
        resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        articles: list[FetchedArticle] = []

        for entry in feed.entries[:remaining]:
            title = getattr(entry, "title", "Untitled")
            link = getattr(entry, "link", "")
            if not link:
                continue

            raw_content = _extract_content(entry)
            content = normalize_content(raw_content) if raw_content else title

            articles.append(
                FetchedArticle(
                    source=f"rss:{feed_url}",
                    source_url=link,
                    title=title,
                    published_at=_parse_published(entry),
                    content=content,
                    metadata={
                        "feed_url": feed_url,
                        "author": getattr(entry, "author", None),
                        "tags": [
                            t.get("term", "") for t in getattr(entry, "tags", [])
                        ],
                    },
                )
            )

        logger.info("Parsed %d articles from %s", len(articles), feed_url)
        return articles

    @staticmethod
    def _parse_feed_urls(news_sources: str) -> list[str]:
        """Parse NEWS_SOURCES config string into a list of feed URLs.

        Format: 'rss:https://url1,rss:https://url2'
        """
        urls: list[str] = []
        for source in news_sources.split(","):
            source = source.strip()
            if source.startswith("rss:"):
                urls.append(source[4:])
            elif source.startswith("http"):
                urls.append(source)
        return urls
