"""Sentiment scoring (FinBERT / LLM / mock).

Scores text as positive, negative, or neutral with a confidence score.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass

from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SentimentResult:
    """Result of scoring a single text."""

    label: str  # "positive", "negative", "neutral"
    score: float  # -1.0 to 1.0 (negative to positive)
    confidence: float  # 0.0 to 1.0


class SentimentProvider(abc.ABC):
    """Abstract interface for sentiment scoring."""

    @abc.abstractmethod
    async def score(self, texts: list[str]) -> list[SentimentResult]:
        """Score a batch of texts. Returns one SentimentResult per input."""


class MockSentimentProvider(SentimentProvider):
    """Returns neutral sentiment for everything. For testing only."""

    async def score(self, texts: list[str]) -> list[SentimentResult]:
        return [
            SentimentResult(label="neutral", score=0.0, confidence=0.5)
            for _ in texts
        ]


class FinBERTSentimentProvider(SentimentProvider):
    """Scores sentiment using ProsusAI/finbert.

    Requires `transformers` and `torch` (install via pip install quant-news-rag[sentiment]).
    The model is lazy-loaded on first call.
    """

    _pipeline = None

    def _get_pipeline(self):
        if FinBERTSentimentProvider._pipeline is None:
            from transformers import pipeline

            logger.info("Loading FinBERT model (first call, may take a moment)...")
            FinBERTSentimentProvider._pipeline = pipeline(
                "sentiment-analysis",
                model="ProsusAI/finbert",
                tokenizer="ProsusAI/finbert",
                truncation=True,
                max_length=512,
            )
        return FinBERTSentimentProvider._pipeline

    async def score(self, texts: list[str]) -> list[SentimentResult]:
        pipe = self._get_pipeline()

        # FinBERT returns labels: positive, negative, neutral
        raw_results = pipe(texts, batch_size=16)

        results: list[SentimentResult] = []
        for raw in raw_results:
            label = raw["label"].lower()
            confidence = float(raw["score"])

            # Map to -1 to 1 scale
            if label == "positive":
                score = confidence
            elif label == "negative":
                score = -confidence
            else:
                score = 0.0

            results.append(
                SentimentResult(label=label, score=score, confidence=confidence)
            )

        return results


class LLMSentimentProvider(SentimentProvider):
    """Scores sentiment using an LLM API call.

    Placeholder — requires an LLM client to be wired in.
    Falls back to mock behavior until implemented.
    """

    async def score(self, texts: list[str]) -> list[SentimentResult]:
        logger.warning("LLM sentiment provider not fully implemented, returning neutral")
        return [
            SentimentResult(label="neutral", score=0.0, confidence=0.3)
            for _ in texts
        ]


def get_sentiment_provider() -> SentimentProvider:
    """Factory that returns the configured sentiment provider."""
    provider = get_settings().SENTIMENT_PROVIDER.lower()
    if provider == "mock":
        return MockSentimentProvider()
    elif provider == "finbert":
        return FinBERTSentimentProvider()
    elif provider == "llm":
        return LLMSentimentProvider()
    else:
        raise ValueError(f"Unknown SENTIMENT_PROVIDER: {provider!r}")


async def score_documents(
    texts: list[str],
    provider: SentimentProvider | None = None,
) -> list[SentimentResult]:
    """High-level: score a batch of texts using the configured provider."""
    if provider is None:
        provider = get_sentiment_provider()
    return await provider.score(texts)
