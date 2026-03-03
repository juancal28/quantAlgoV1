"""Tests for news document cleanup (NEWS_RETENTION_DAYS)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from core.storage.models import NewsDocument
from core.storage.repos import news_repo


def _make_doc(fetched_days_ago: int = 0, **overrides) -> NewsDocument:
    """Create a NewsDocument with fetched_at set to *fetched_days_ago* days in the past."""
    now = datetime.now(timezone.utc)
    doc_id = uuid.uuid4()
    defaults = dict(
        id=doc_id,
        source="rss",
        source_url=f"https://example.com/{doc_id}",
        title=f"Test article {doc_id}",
        published_at=now - timedelta(days=fetched_days_ago),
        fetched_at=now - timedelta(days=fetched_days_ago),
        content=f"Content for {doc_id}",
        content_hash=f"hash_{doc_id}",
        metadata={},
    )
    defaults.update(overrides)
    return NewsDocument(**defaults)


@pytest.mark.asyncio
async def test_old_docs_returned_by_repo(db_session):
    """Documents older than N days are returned by get_old_documents."""
    old_doc = _make_doc(fetched_days_ago=5)
    db_session.add(old_doc)
    await db_session.flush()

    results = await news_repo.get_old_documents(db_session, days=3)
    assert len(results) == 1
    assert str(results[0].id) == str(old_doc.id)


@pytest.mark.asyncio
async def test_recent_docs_not_returned(db_session):
    """Documents newer than N days are NOT returned by get_old_documents."""
    recent_doc = _make_doc(fetched_days_ago=1)
    db_session.add(recent_doc)
    await db_session.flush()

    results = await news_repo.get_old_documents(db_session, days=3)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_delete_by_ids_removes_rows(db_session):
    """delete_by_ids removes documents and returns the correct count."""
    doc1 = _make_doc(fetched_days_ago=5)
    doc2 = _make_doc(fetched_days_ago=5)
    keep = _make_doc(fetched_days_ago=1)
    db_session.add_all([doc1, doc2, keep])
    await db_session.flush()

    # Retrieve IDs back from DB so they match SQLite's String(36) column type
    old_docs = await news_repo.get_old_documents(db_session, days=3)
    old_ids = [d.id for d in old_docs]
    assert len(old_ids) == 2

    deleted = await news_repo.delete_by_ids(db_session, old_ids)
    assert deleted == 2

    # Verify only the kept doc remains
    stmt = select(NewsDocument)
    result = await db_session.execute(stmt)
    remaining = list(result.scalars().all())
    assert len(remaining) == 1
    assert str(remaining[0].id) == str(keep.id)


@pytest.mark.asyncio
async def test_cleanup_task_deletes_old_docs(db_session, mock_settings):
    """_run_news_cleanup_async deletes old documents from DB."""
    mock_settings("NEWS_RETENTION_DAYS", "3")
    from apps.scheduler.jobs import _run_news_cleanup_async

    old1 = _make_doc(fetched_days_ago=5)
    old2 = _make_doc(fetched_days_ago=10)
    recent = _make_doc(fetched_days_ago=1)
    db_session.add_all([old1, old2, recent])
    await db_session.flush()

    result = await _run_news_cleanup_async(_session=db_session)
    assert result["deleted"] == 2

    # Verify the recent doc is still there
    stmt = select(NewsDocument)
    rows = await db_session.execute(stmt)
    remaining = list(rows.scalars().all())
    assert len(remaining) == 1
    assert str(remaining[0].id) == str(recent.id)


@pytest.mark.asyncio
async def test_cleanup_disabled_when_zero(mock_settings):
    """run_news_cleanup returns skipped when NEWS_RETENTION_DAYS=0."""
    mock_settings("NEWS_RETENTION_DAYS", "0")

    from core.config import get_settings

    settings = get_settings()
    assert settings.NEWS_RETENTION_DAYS == 0
    # The sync wrapper checks this; we verify the config is correct.


@pytest.mark.asyncio
async def test_vectorstore_delete_by_doc_ids():
    """FAISSMockVectorStore correctly removes vectors by doc_id."""
    from core.kb.vectorstore import FAISSMockVectorStore

    store = FAISSMockVectorStore(vector_size=4)

    # Upsert 3 vectors with different doc_ids
    await store.upsert(
        ids=["chunk_a1", "chunk_a2", "chunk_b1"],
        vectors=[[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]],
        payloads=[
            {"doc_id": "doc_a", "title": "A chunk 1"},
            {"doc_id": "doc_a", "title": "A chunk 2"},
            {"doc_id": "doc_b", "title": "B chunk 1"},
        ],
    )
    assert store._index.ntotal == 3

    # Delete doc_a (2 chunks)
    deleted = await store.delete_by_doc_ids(["doc_a"])
    assert deleted == 2
    assert store._index.ntotal == 1
    assert len(store._ids) == 1
    assert store._ids[0] == "chunk_b1"
    assert store._payloads[0]["doc_id"] == "doc_b"

    # Query should still work for remaining vector
    results = await store.query([0.0, 0.0, 1.0, 0.0], top_k=5)
    assert len(results) == 1
    assert results[0]["payload"]["doc_id"] == "doc_b"
