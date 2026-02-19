"""Embedding provider abstraction with mock and OpenAI implementations."""

from __future__ import annotations

import abc

from core.config import get_settings


class EmbeddingProvider(abc.ABC):
    """Abstract interface for text embedding."""

    @abc.abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns a list of vectors."""

    @abc.abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimensionality."""


class MockEmbeddingProvider(EmbeddingProvider):
    """Returns zero vectors of the configured size. For testing only."""

    def __init__(self) -> None:
        self._dim = get_settings().VECTOR_SIZE

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self._dim for _ in texts]

    def dimension(self) -> int:
        return self._dim


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI text-embedding-3-small via httpx."""

    MODEL = "text-embedding-3-small"

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.OPENAI_API_KEY
        self._dim = settings.VECTOR_SIZE
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI embedding provider")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"input": texts, "model": self.MODEL},
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
        return [item["embedding"] for item in data["data"]]

    def dimension(self) -> int:
        return self._dim


def get_embedding_provider() -> EmbeddingProvider:
    """Factory that returns the embedding provider based on config."""
    provider = get_settings().EMBEDDINGS_PROVIDER.lower()
    if provider == "mock":
        return MockEmbeddingProvider()
    elif provider == "openai":
        return OpenAIEmbeddingProvider()
    else:
        raise ValueError(f"Unknown EMBEDDINGS_PROVIDER: {provider!r}")
