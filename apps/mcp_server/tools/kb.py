"""Knowledge base embed/upsert and query MCP tools."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.mcp_server.schemas import (
    EmbedInput,
    EmbedOutput,
    QueryInput,
    QueryOutput,
    QueryResultItem,
)
from core.kb.chunking import chunk_text
from core.kb.embeddings import EmbeddingProvider, get_embedding_provider
from core.kb.vectorstore import VectorStoreBase, get_vectorstore
from core.logging import get_logger
from core.storage.models import NewsDocument

logger = get_logger(__name__)


async def embed_and_upsert_docs(
    session: AsyncSession,
    params: EmbedInput,
    store: VectorStoreBase | None = None,
    embedder: EmbeddingProvider | None = None,
) -> EmbedOutput:
    """Chunk documents, embed them, and upsert into the vector store.

    Returns the total number of chunks upserted.
    """
    if store is None:
        store = get_vectorstore()
    if embedder is None:
        embedder = get_embedding_provider()

    await store.ensure_collection()
    total_upserted = 0

    for doc_id_str in params.doc_ids:
        doc = await session.get(NewsDocument, uuid.UUID(doc_id_str))
        if doc is None:
            logger.warning("Document not found: %s", doc_id_str)
            continue

        chunks = chunk_text(doc.content)
        if not chunks:
            continue

        vectors = await embedder.embed(chunks)

        # Qdrant requires UUIDs or unsigned ints as point IDs.
        # Generate deterministic UUIDs from doc_id + chunk_index.
        ids = [
            str(uuid.uuid5(uuid.UUID(doc_id_str), f"chunk_{i}"))
            for i in range(len(chunks))
        ]
        payloads = [
            {
                "doc_id": doc_id_str,
                "title": doc.title,
                "source": doc.source,
                "source_url": doc.source_url,
                "published_at": doc.published_at.isoformat() if doc.published_at else "",
                "tickers": (doc.metadata_ or {}).get("tickers", []),
                "tags": (doc.metadata_ or {}).get("tags", []),
                "sentiment_score": doc.sentiment_score,
                "sentiment_label": doc.sentiment_label,
                "chunk_index": i,
                "chunk_total": len(chunks),
                "snippet": chunk[:200],
            }
            for i, chunk in enumerate(chunks)
        ]

        count = await store.upsert(ids, vectors, payloads)
        total_upserted += count

    logger.info("Upserted %d chunks to vector store", total_upserted)
    return EmbedOutput(upserted_chunks=total_upserted)


async def query_kb(
    params: QueryInput,
    store: VectorStoreBase | None = None,
    embedder: EmbeddingProvider | None = None,
) -> QueryOutput:
    """Query the knowledge base for relevant documents.

    Returns scored results with snippets.
    """
    if store is None:
        store = get_vectorstore()
    if embedder is None:
        embedder = get_embedding_provider()

    vectors = await embedder.embed([params.query])
    raw_results = await store.query(
        vectors[0], top_k=params.top_k, filters=params.filters
    )

    results = [
        QueryResultItem(
            doc_id=r["payload"].get("doc_id", r["id"]),
            title=r["payload"].get("title", ""),
            score=r["score"],
            snippet=r["payload"].get("snippet", ""),
            published_at=r["payload"].get("published_at", ""),
            source_url=r["payload"].get("source_url", ""),
            sentiment_score=r["payload"].get("sentiment_score"),
        )
        for r in raw_results
    ]

    return QueryOutput(results=results)
