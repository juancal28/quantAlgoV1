"""Smoke tests to verify the foundation build is importable and functional."""

from __future__ import annotations


def test_config_loads():
    """Settings singleton loads and TRADING_MODE is paper."""
    from core.config import get_settings

    s = get_settings()
    assert s.TRADING_MODE == "paper"
    assert isinstance(s.approved_universe_list, list)
    assert "SPY" in s.approved_universe_list


def test_models_importable():
    """All six ORM models can be imported."""
    from core.storage.models import (
        Base,
        MarketBar,
        NewsDocument,
        PnlSnapshot,
        Run,
        StrategyAuditLog,
        StrategyVersion,
    )

    tables = Base.metadata.tables
    assert "news_documents" in tables
    assert "market_bars" in tables
    assert "strategy_versions" in tables
    assert "strategy_audit_log" in tables
    assert "pnl_snapshots" in tables
    assert "runs" in tables


def test_chunking_deterministic():
    """chunk_text produces the same output on repeated calls."""
    from core.kb.chunking import chunk_text

    text = "A" * 2500
    c1 = chunk_text(text, chunk_size=1000, overlap=150)
    c2 = chunk_text(text, chunk_size=1000, overlap=150)
    assert c1 == c2
    assert len(c1) == 3  # 0-1000, 850-1850, 1700-2500


def test_chunking_overlap():
    """Consecutive chunks overlap by the expected amount."""
    from core.kb.chunking import chunk_text

    text = "".join(str(i % 10) for i in range(2000))
    chunks = chunk_text(text, chunk_size=1000, overlap=150)
    # 2000 chars, step=850 → starts at 0, 850, 1700 → 3 chunks
    assert len(chunks) == 3
    # Last 150 chars of chunk 0 == first 150 chars of chunk 1
    assert chunks[0][-150:] == chunks[1][:150]
    assert chunks[1][-150:] == chunks[2][:150]


def test_embedding_mock():
    """Mock embedding provider returns zero vectors of correct dimension."""
    import asyncio

    from core.kb.embeddings import get_embedding_provider

    provider = get_embedding_provider()
    vecs = asyncio.get_event_loop().run_until_complete(
        provider.embed(["test sentence"])
    )
    assert len(vecs) == 1
    assert len(vecs[0]) == 1536
    assert all(v == 0.0 for v in vecs[0])


async def test_faiss_mock_vectorstore():
    """FAISS mock store can upsert and query."""
    from core.kb.vectorstore import FAISSMockVectorStore

    store = FAISSMockVectorStore(vector_size=4)
    await store.ensure_collection()

    ids = ["a", "b"]
    vecs = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
    payloads = [{"title": "doc_a"}, {"title": "doc_b"}]
    count = await store.upsert(ids, vecs, payloads)
    assert count == 2

    results = await store.query([1.0, 0.0, 0.0, 0.0], top_k=2)
    assert len(results) == 2
    assert results[0]["id"] == "a"
    assert results[0]["score"] > results[1]["score"]


async def test_db_session_creates_tables(db_session):
    """The db_session fixture creates tables and yields a working session."""
    from sqlalchemy import text

    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1
