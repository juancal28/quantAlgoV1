"""Proposal quality scoring — replaces the backtest gate in the news cycle pipeline.

Evaluates the evidence backing a RAG agent proposal across four dimensions:
  1. Evidence strength: how many cited documents support the proposal
  2. Recency: how fresh the cited documents are
  3. Sentiment consensus: how much the cited docs agree in sentiment direction
  4. Coverage: what fraction of the proposed universe is mentioned in docs

Each dimension scores 0.0–1.0. The composite is a weighted sum.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.storage.repos import news_repo


@dataclass
class QualityDimension:
    """A single scoring dimension."""

    name: str
    score: float
    weight: float
    detail: str


@dataclass
class QualityScore:
    """Composite quality score with breakdown."""

    dimensions: list[QualityDimension] = field(default_factory=list)
    composite: float = 0.0
    passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "composite": round(self.composite, 4),
            "passed": self.passed,
            "dimensions": {
                dim.name: {
                    "score": round(dim.score, 4),
                    "weight": dim.weight,
                    "detail": dim.detail,
                }
                for dim in self.dimensions
            },
        }


def _parse_doc_ids(raw_ids: list) -> list[uuid.UUID]:
    """Convert string doc IDs to UUIDs, skipping invalid ones."""
    parsed: list[uuid.UUID] = []
    for rid in raw_ids:
        if isinstance(rid, uuid.UUID):
            parsed.append(rid)
            continue
        try:
            parsed.append(uuid.UUID(str(rid)))
        except (ValueError, AttributeError):
            pass
    return parsed


async def score_proposal_quality(
    session: AsyncSession,
    proposal: dict,
    new_definition: dict,
    settings: Settings | None = None,
) -> QualityScore:
    """Score a RAG agent proposal on evidence quality.

    Args:
        session: DB session for fetching cited documents.
        proposal: The agent's proposal dict (must have cited_doc_ids).
        new_definition: The proposed strategy definition (must have universe).
        settings: Optional settings override (for testing).

    Returns:
        QualityScore with four dimensions and a composite.
    """
    s = settings or get_settings()
    now = datetime.now(timezone.utc)

    # Parse cited doc IDs
    raw_cited = proposal.get("cited_doc_ids", [])
    cited_ids = _parse_doc_ids(raw_cited)

    # Fetch cited documents from DB
    docs = await news_repo.get_by_ids(session, cited_ids) if cited_ids else []
    found_count = len(docs)

    # --- 1. Evidence strength ---
    evidence_score = min(1.0, found_count / s.QUALITY_MIN_CITED_DOCS) if s.QUALITY_MIN_CITED_DOCS > 0 else 1.0
    evidence_dim = QualityDimension(
        name="evidence",
        score=evidence_score,
        weight=s.QUALITY_WEIGHT_EVIDENCE,
        detail=f"{found_count} cited docs found (need {s.QUALITY_MIN_CITED_DOCS})",
    )

    # --- 2. Recency ---
    if docs:
        ages_minutes: list[float] = []
        for doc in docs:
            pub = doc.published_at or doc.fetched_at
            if pub is not None:
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                age = (now - pub).total_seconds() / 60.0
                ages_minutes.append(max(0.0, age))
        if ages_minutes:
            avg_age = sum(ages_minutes) / len(ages_minutes)
            recency_score = max(0.0, min(1.0, 1.0 - avg_age / s.QUALITY_RECENCY_LOOKBACK_MINUTES))
        else:
            recency_score = 0.0
    else:
        recency_score = 0.0
    recency_dim = QualityDimension(
        name="recency",
        score=recency_score,
        weight=s.QUALITY_WEIGHT_RECENCY,
        detail=f"avg age {avg_age:.0f}m (lookback {s.QUALITY_RECENCY_LOOKBACK_MINUTES}m)" if docs and ages_minutes else "no docs",
    )

    # --- 3. Sentiment consensus ---
    sentiment_scores: list[float] = []
    for doc in docs:
        if doc.sentiment_score is not None:
            sentiment_scores.append(float(doc.sentiment_score))
    if len(sentiment_scores) >= 2:
        std = statistics.stdev(sentiment_scores)
        consensus_score = max(0.0, min(1.0, 1.0 - std))
    elif len(sentiment_scores) == 1:
        consensus_score = 1.0  # single doc = perfect agreement
    else:
        consensus_score = 0.0
    consensus_dim = QualityDimension(
        name="consensus",
        score=consensus_score,
        weight=s.QUALITY_WEIGHT_CONSENSUS,
        detail=f"std={std:.3f} across {len(sentiment_scores)} scores" if len(sentiment_scores) >= 2 else f"{len(sentiment_scores)} sentiment scores",
    )

    # --- 4. Coverage ---
    universe = new_definition.get("universe", [])
    if universe:
        tickers_in_docs: set[str] = set()
        for doc in docs:
            meta = doc.metadata_ if hasattr(doc, "metadata_") else (doc.metadata or {})
            if isinstance(meta, dict):
                for t in meta.get("tickers", []):
                    tickers_in_docs.add(t)
        coverage_score = min(1.0, len(tickers_in_docs) / len(universe))
    else:
        coverage_score = 0.0
    coverage_dim = QualityDimension(
        name="coverage",
        score=coverage_score,
        weight=s.QUALITY_WEIGHT_COVERAGE,
        detail=f"{len(tickers_in_docs) if universe else 0}/{len(universe)} universe tickers in docs",
    )

    # --- Composite ---
    dimensions = [evidence_dim, recency_dim, consensus_dim, coverage_dim]
    composite = sum(d.score * d.weight for d in dimensions)
    passed = composite >= s.QUALITY_MIN_COMPOSITE_SCORE

    return QualityScore(
        dimensions=dimensions,
        composite=composite,
        passed=passed,
    )
