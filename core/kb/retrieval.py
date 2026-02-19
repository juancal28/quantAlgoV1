"""Knowledge base retrieval — embed query then search vector store."""

from __future__ import annotations

from typing import Any

from core.kb.embeddings import EmbeddingProvider
from core.kb.vectorstore import VectorStoreBase


async def query_knowledge_base(
    store: VectorStoreBase,
    embedder: EmbeddingProvider,
    query: str,
    top_k: int = 10,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Embed the query string and search the vector store.

    Returns a list of results with keys: id, score, payload.
    """
    vectors = await embedder.embed([query])
    return await store.query(vectors[0], top_k=top_k, filters=filters)
