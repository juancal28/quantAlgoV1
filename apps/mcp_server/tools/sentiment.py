"""Sentiment scoring MCP tool."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.mcp_server.schemas import SentimentInput, SentimentOutput
from core.kb.sentiment import SentimentProvider, get_sentiment_provider
from core.logging import get_logger
from core.storage.models import NewsDocument

logger = get_logger(__name__)


async def score_sentiment(
    session: AsyncSession,
    params: SentimentInput,
    provider: SentimentProvider | None = None,
) -> SentimentOutput:
    """Score sentiment for a list of documents and update them in the DB.

    Returns the count of scored documents.
    """
    if provider is None:
        provider = get_sentiment_provider()

    docs: list[NewsDocument] = []
    texts: list[str] = []

    for doc_id_str in params.doc_ids:
        doc = await session.get(NewsDocument, uuid.UUID(doc_id_str))
        if doc is None:
            logger.warning("Document not found: %s", doc_id_str)
            continue
        docs.append(doc)
        texts.append(doc.content)

    if not texts:
        return SentimentOutput(scored=0)

    results = await provider.score(texts)

    for doc, result in zip(docs, results):
        doc.sentiment_score = result.score
        doc.sentiment_label = result.label

    await session.commit()
    logger.info("Scored sentiment for %d documents", len(docs))
    return SentimentOutput(scored=len(docs))
