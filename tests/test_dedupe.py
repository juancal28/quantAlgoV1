"""Tests for deduplication logic."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.ingestion.dedupe import compute_content_hash, is_duplicate


def test_same_content_same_hash():
    """Same content produces the same hash."""
    h1 = compute_content_hash("Breaking: AAPL hits all-time high")
    h2 = compute_content_hash("Breaking: AAPL hits all-time high")
    assert h1 == h2


def test_different_content_different_hash():
    """Different content produces different hashes."""
    h1 = compute_content_hash("AAPL hits all-time high")
    h2 = compute_content_hash("MSFT reports earnings beat")
    assert h1 != h2


def test_html_normalized_before_hash():
    """HTML is stripped before hashing, so same text with/without tags matches."""
    h1 = compute_content_hash("<p>AAPL hits <b>all-time high</b></p>")
    h2 = compute_content_hash("AAPL hits all-time high")
    assert h1 == h2


def test_whitespace_normalized_before_hash():
    """Extra whitespace is collapsed before hashing."""
    h1 = compute_content_hash("AAPL   hits   all-time   high")
    h2 = compute_content_hash("AAPL hits all-time high")
    assert h1 == h2


async def test_duplicate_url_detected(db_session):
    """A document with the same URL is detected as duplicate."""
    from core.storage.models import NewsDocument

    doc = NewsDocument(
        id=uuid.uuid4(),
        source="test",
        source_url="https://example.com/article-1",
        title="Test Article",
        published_at=datetime.now(timezone.utc),
        content="Some content here",
        content_hash=compute_content_hash("Some content here"),
    )
    db_session.add(doc)
    await db_session.commit()

    result = await is_duplicate(
        db_session, "https://example.com/article-1", "Completely different content"
    )
    assert result is True


async def test_duplicate_content_detected(db_session):
    """A document with the same content hash is detected as duplicate."""
    from core.storage.models import NewsDocument

    content = "AAPL announced record quarterly earnings"
    doc = NewsDocument(
        id=uuid.uuid4(),
        source="test",
        source_url="https://example.com/article-1",
        title="Test Article",
        published_at=datetime.now(timezone.utc),
        content=content,
        content_hash=compute_content_hash(content),
    )
    db_session.add(doc)
    await db_session.commit()

    result = await is_duplicate(
        db_session, "https://other-site.com/same-story", content
    )
    assert result is True


async def test_unique_content_not_flagged(db_session):
    """A genuinely new document is not flagged as duplicate."""
    result = await is_duplicate(
        db_session, "https://example.com/brand-new", "Never seen before content"
    )
    assert result is False
