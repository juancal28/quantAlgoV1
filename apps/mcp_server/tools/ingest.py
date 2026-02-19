"""News ingestion MCP tool."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from apps.mcp_server.schemas import IngestInput, IngestOutput
from core.ingestion.dedupe import compute_content_hash, is_duplicate
from core.ingestion.fetchers.rss import RSSFetcher
from core.ingestion.ticker_extract import extract_tickers
from core.logging import get_logger
from core.storage.models import NewsDocument

logger = get_logger(__name__)


async def ingest_latest_news(
    session: AsyncSession,
    params: IngestInput,
) -> IngestOutput:
    """Fetch articles from RSS, deduplicate, extract tickers, and store.

    Returns the count and IDs of newly ingested documents.
    """
    fetcher = RSSFetcher()
    articles = await fetcher.fetch(max_items=params.max_items)
    logger.info("Fetched %d raw articles", len(articles))

    ingested_ids: list[str] = []

    for article in articles:
        if await is_duplicate(session, article.source_url, article.content):
            logger.debug("Skipping duplicate: %s", article.source_url)
            continue

        content_hash = compute_content_hash(article.content)
        tickers = extract_tickers(article.content)

        metadata = {**article.metadata, "tickers": tickers}

        doc = NewsDocument(
            id=uuid.uuid4(),
            source=article.source,
            source_url=article.source_url,
            title=article.title,
            published_at=article.published_at,
            fetched_at=datetime.now(timezone.utc),
            content=article.content,
            content_hash=content_hash,
            metadata_=metadata,
        )
        session.add(doc)
        ingested_ids.append(str(doc.id))

    if ingested_ids:
        await session.commit()

    logger.info("Ingested %d new documents", len(ingested_ids))
    return IngestOutput(ingested=len(ingested_ids), doc_ids=ingested_ids)
