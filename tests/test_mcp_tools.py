"""Tests for MCP tools (using mocks, no external services)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from apps.mcp_server.schemas import (
    EmbedInput,
    QueryInput,
    SentimentInput,
)
from core.ingestion.dedupe import compute_content_hash
from core.kb.embeddings import MockEmbeddingProvider
from core.kb.sentiment import MockSentimentProvider
from core.kb.vectorstore import FAISSMockVectorStore
from core.storage.models import NewsDocument


async def _insert_test_doc(session, content="AAPL stock surged 5% today") -> str:
    """Helper: insert a test document and return its ID as string."""
    doc_id = uuid.uuid4()
    doc = NewsDocument(
        id=doc_id,
        source="test",
        source_url=f"https://example.com/{doc_id}",
        title="Test Article",
        published_at=datetime.now(timezone.utc),
        content=content,
        content_hash=compute_content_hash(content),
    )
    session.add(doc)
    await session.commit()
    return str(doc_id)


async def test_embed_and_upsert(db_session):
    """embed_and_upsert_docs chunks a document and upserts vectors."""
    from apps.mcp_server.tools.kb import embed_and_upsert_docs

    doc_id = await _insert_test_doc(db_session, content="A" * 1200)

    store = FAISSMockVectorStore(vector_size=1536)
    embedder = MockEmbeddingProvider()

    result = await embed_and_upsert_docs(
        db_session,
        EmbedInput(doc_ids=[doc_id]),
        store=store,
        embedder=embedder,
    )

    # 1200 chars with 1000 chunk_size / 150 overlap → 2 chunks
    assert result.upserted_chunks == 2


async def test_embed_missing_doc(db_session):
    """embed_and_upsert_docs handles missing documents gracefully."""
    from apps.mcp_server.tools.kb import embed_and_upsert_docs

    store = FAISSMockVectorStore(vector_size=1536)
    embedder = MockEmbeddingProvider()

    result = await embed_and_upsert_docs(
        db_session,
        EmbedInput(doc_ids=["00000000-0000-0000-0000-000000000000"]),
        store=store,
        embedder=embedder,
    )

    assert result.upserted_chunks == 0


async def test_score_sentiment_mock(db_session):
    """score_sentiment updates documents with sentiment scores."""
    from apps.mcp_server.tools.sentiment import score_sentiment

    doc_id = await _insert_test_doc(db_session)

    result = await score_sentiment(
        db_session,
        SentimentInput(doc_ids=[doc_id]),
        provider=MockSentimentProvider(),
    )

    assert result.scored == 1

    # Verify the document was updated
    doc = await db_session.get(NewsDocument, uuid.UUID(doc_id))
    assert doc.sentiment_label == "neutral"
    assert doc.sentiment_score == 0.0


async def test_query_kb_returns_results():
    """query_kb returns results from the vector store."""
    from apps.mcp_server.tools.kb import query_kb

    store = FAISSMockVectorStore(vector_size=4)
    embedder = MockEmbeddingProvider()
    # Override dimension for this test
    embedder._dim = 4

    # Insert a document into the store
    await store.upsert(
        ids=["doc1_chunk_0"],
        vectors=[[1.0, 0.0, 0.0, 0.0]],
        payloads=[{
            "doc_id": "doc1",
            "title": "Test Doc",
            "snippet": "AAPL surged today",
            "published_at": "2025-01-15T00:00:00Z",
            "source_url": "https://example.com/1",
            "sentiment_score": 0.8,
        }],
    )

    result = await query_kb(
        QueryInput(query="test", top_k=5),
        store=store,
        embedder=embedder,
    )

    assert len(result.results) == 1
    assert result.results[0].doc_id == "doc1"
    assert result.results[0].title == "Test Doc"


def test_schemas_serializable():
    """All schemas can be serialized to JSON schema (for MCP tool registration)."""
    from apps.mcp_server.schemas import (
        EmbedInput,
        IngestInput,
        QueryInput,
        SentimentInput,
    )

    for schema_cls in [IngestInput, EmbedInput, SentimentInput, QueryInput]:
        js = schema_cls.model_json_schema()
        assert "properties" in js
