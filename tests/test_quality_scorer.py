"""Tests for core.agent.quality_scorer."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.agent.quality_scorer import QualityScore, score_proposal_quality
from core.config import Settings
from core.storage.models import NewsDocument


def _make_doc(
    *,
    age_minutes: float = 30,
    sentiment: float | None = 0.5,
    tickers: list[str] | None = None,
) -> NewsDocument:
    """Create a NewsDocument with sensible defaults."""
    now = datetime.now(timezone.utc)
    return NewsDocument(
        id=uuid.uuid4(),
        source="test",
        source_url=f"https://example.com/{uuid.uuid4()}",
        title="Test headline",
        published_at=now - timedelta(minutes=age_minutes),
        fetched_at=now - timedelta(minutes=age_minutes),
        content="Test content body.",
        content_hash=uuid.uuid4().hex,
        metadata_={"tickers": tickers or []},
        sentiment_score=sentiment,
        sentiment_label="positive" if sentiment and sentiment > 0 else "neutral",
    )


def _make_settings(**overrides) -> Settings:
    """Build a Settings object with test defaults."""
    defaults = {
        "TRADING_MODE": "paper",
        "QUALITY_MIN_COMPOSITE_SCORE": 0.5,
        "QUALITY_MIN_CITED_DOCS": 3,
        "QUALITY_RECENCY_LOOKBACK_MINUTES": 480,
        "QUALITY_WEIGHT_EVIDENCE": 0.30,
        "QUALITY_WEIGHT_RECENCY": 0.25,
        "QUALITY_WEIGHT_CONSENSUS": 0.25,
        "QUALITY_WEIGHT_COVERAGE": 0.20,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _make_proposal(doc_ids: list[uuid.UUID]) -> dict:
    return {
        "cited_doc_ids": [str(d) for d in doc_ids],
        "confidence": 0.8,
        "rationale": "test rationale",
    }


def _make_definition(universe: list[str] | None = None) -> dict:
    return {
        "name": "test_strategy",
        "universe": universe or ["SPY", "QQQ"],
    }


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_perfect_score(db_session):
    """5+ cited docs, recent, consistent sentiment, full ticker coverage."""
    docs = [
        _make_doc(age_minutes=10, sentiment=0.7, tickers=["SPY"]),
        _make_doc(age_minutes=20, sentiment=0.65, tickers=["QQQ"]),
        _make_doc(age_minutes=30, sentiment=0.72, tickers=["SPY", "QQQ"]),
        _make_doc(age_minutes=15, sentiment=0.68, tickers=["SPY"]),
        _make_doc(age_minutes=25, sentiment=0.71, tickers=["QQQ"]),
    ]
    for d in docs:
        db_session.add(d)
    await db_session.flush()

    proposal = _make_proposal([d.id for d in docs])
    definition = _make_definition(["SPY", "QQQ"])
    settings = _make_settings()

    result = await score_proposal_quality(
        db_session, proposal, definition, settings=settings
    )

    assert isinstance(result, QualityScore)
    assert result.composite > 0.7
    assert result.passed is True
    assert len(result.dimensions) == 4

    # Evidence should be perfect (5 >= 3)
    evidence = next(d for d in result.dimensions if d.name == "evidence")
    assert evidence.score == 1.0

    # Coverage should be perfect (both SPY and QQQ mentioned)
    coverage = next(d for d in result.dimensions if d.name == "coverage")
    assert coverage.score == 1.0


@pytest.mark.asyncio
async def test_zero_evidence(db_session):
    """Empty cited_doc_ids -> evidence = 0.0."""
    proposal = _make_proposal([])
    definition = _make_definition()
    settings = _make_settings()

    result = await score_proposal_quality(
        db_session, proposal, definition, settings=settings
    )

    evidence = next(d for d in result.dimensions if d.name == "evidence")
    assert evidence.score == 0.0
    assert result.composite < 0.5
    assert result.passed is False


@pytest.mark.asyncio
async def test_old_docs_low_recency(db_session):
    """Docs older than lookback -> recency near 0.0."""
    docs = [
        _make_doc(age_minutes=600, sentiment=0.5, tickers=["SPY"]),
        _make_doc(age_minutes=700, sentiment=0.5, tickers=["QQQ"]),
        _make_doc(age_minutes=800, sentiment=0.5, tickers=["SPY"]),
    ]
    for d in docs:
        db_session.add(d)
    await db_session.flush()

    proposal = _make_proposal([d.id for d in docs])
    definition = _make_definition()
    settings = _make_settings(QUALITY_RECENCY_LOOKBACK_MINUTES=480)

    result = await score_proposal_quality(
        db_session, proposal, definition, settings=settings
    )

    recency = next(d for d in result.dimensions if d.name == "recency")
    assert recency.score == 0.0  # all docs older than 480min -> clamped to 0


@pytest.mark.asyncio
async def test_mixed_sentiment_low_consensus(db_session):
    """High std dev in sentiment -> consensus near 0.0."""
    docs = [
        _make_doc(sentiment=0.9, tickers=["SPY"]),
        _make_doc(sentiment=-0.8, tickers=["QQQ"]),
        _make_doc(sentiment=0.1, tickers=["SPY"]),
    ]
    for d in docs:
        db_session.add(d)
    await db_session.flush()

    proposal = _make_proposal([d.id for d in docs])
    definition = _make_definition()
    settings = _make_settings()

    result = await score_proposal_quality(
        db_session, proposal, definition, settings=settings
    )

    consensus = next(d for d in result.dimensions if d.name == "consensus")
    assert consensus.score < 0.3  # high disagreement


@pytest.mark.asyncio
async def test_partial_coverage(db_session):
    """Only some universe tickers in docs."""
    docs = [
        _make_doc(tickers=["SPY"]),
        _make_doc(tickers=["SPY"]),
        _make_doc(tickers=["SPY"]),
    ]
    for d in docs:
        db_session.add(d)
    await db_session.flush()

    proposal = _make_proposal([d.id for d in docs])
    definition = _make_definition(["SPY", "QQQ", "AAPL", "MSFT"])
    settings = _make_settings()

    result = await score_proposal_quality(
        db_session, proposal, definition, settings=settings
    )

    coverage = next(d for d in result.dimensions if d.name == "coverage")
    assert coverage.score == 0.25  # 1 out of 4 tickers


@pytest.mark.asyncio
async def test_below_threshold_fails(db_session):
    """Composite below threshold -> passed=False."""
    docs = [_make_doc(age_minutes=600, sentiment=None, tickers=[])]
    for d in docs:
        db_session.add(d)
    await db_session.flush()

    proposal = _make_proposal([d.id for d in docs])
    definition = _make_definition()
    settings = _make_settings(QUALITY_MIN_COMPOSITE_SCORE=0.9)

    result = await score_proposal_quality(
        db_session, proposal, definition, settings=settings
    )

    assert result.passed is False
    assert result.composite < 0.9


@pytest.mark.asyncio
async def test_missing_docs_in_db(db_session):
    """Cited IDs that don't exist in DB -> reduces evidence score gracefully."""
    fake_ids = [uuid.uuid4() for _ in range(5)]
    proposal = _make_proposal(fake_ids)
    definition = _make_definition()
    settings = _make_settings()

    result = await score_proposal_quality(
        db_session, proposal, definition, settings=settings
    )

    evidence = next(d for d in result.dimensions if d.name == "evidence")
    assert evidence.score == 0.0  # no docs found
    assert result.passed is False


@pytest.mark.asyncio
async def test_to_dict_serializable(db_session):
    """to_dict() produces a JSON-serializable structure."""
    import json

    docs = [
        _make_doc(sentiment=0.5, tickers=["SPY"]),
        _make_doc(sentiment=0.6, tickers=["QQQ"]),
        _make_doc(sentiment=0.55, tickers=["SPY"]),
    ]
    for d in docs:
        db_session.add(d)
    await db_session.flush()

    proposal = _make_proposal([d.id for d in docs])
    definition = _make_definition()
    settings = _make_settings()

    result = await score_proposal_quality(
        db_session, proposal, definition, settings=settings
    )

    d = result.to_dict()
    # Should be JSON-serializable without errors
    serialized = json.dumps(d)
    assert isinstance(serialized, str)

    # Check structure
    assert "composite" in d
    assert "passed" in d
    assert "dimensions" in d
    assert "evidence" in d["dimensions"]
    assert "recency" in d["dimensions"]
    assert "consensus" in d["dimensions"]
    assert "coverage" in d["dimensions"]


@pytest.mark.asyncio
async def test_invalid_doc_ids_skipped(db_session):
    """Invalid UUID strings in cited_doc_ids are silently skipped."""
    docs = [_make_doc(sentiment=0.5, tickers=["SPY"])]
    for d in docs:
        db_session.add(d)
    await db_session.flush()

    proposal = {
        "cited_doc_ids": [str(docs[0].id), "not-a-uuid", "", "12345"],
        "confidence": 0.8,
    }
    definition = _make_definition()
    settings = _make_settings()

    result = await score_proposal_quality(
        db_session, proposal, definition, settings=settings
    )

    evidence = next(d for d in result.dimensions if d.name == "evidence")
    # Only 1 valid doc found out of min 3
    assert evidence.score == pytest.approx(1.0 / 3.0, abs=0.01)


@pytest.mark.asyncio
async def test_all_none_sentiment(db_session):
    """All docs have None sentiment -> consensus = 0.0."""
    docs = [
        _make_doc(sentiment=None, tickers=["SPY"]),
        _make_doc(sentiment=None, tickers=["QQQ"]),
        _make_doc(sentiment=None, tickers=["SPY"]),
    ]
    for d in docs:
        db_session.add(d)
    await db_session.flush()

    proposal = _make_proposal([d.id for d in docs])
    definition = _make_definition()
    settings = _make_settings()

    result = await score_proposal_quality(
        db_session, proposal, definition, settings=settings
    )

    consensus = next(d for d in result.dimensions if d.name == "consensus")
    assert consensus.score == 0.0
