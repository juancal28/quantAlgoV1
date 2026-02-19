"""Vector store abstraction with Qdrant and FAISS mock implementations."""

from __future__ import annotations

import abc
import uuid
from typing import Any

import numpy as np

from core.config import get_settings


class VectorStoreBase(abc.ABC):
    """Abstract interface for vector storage backends."""

    @abc.abstractmethod
    async def ensure_collection(self) -> None:
        """Create the collection if it doesn't exist."""

    @abc.abstractmethod
    async def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> int:
        """Upsert vectors with payloads. Returns count of upserted points."""

    @abc.abstractmethod
    async def query(
        self,
        vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Query the collection. Returns list of {id, score, payload}."""


class QdrantVectorStore(VectorStoreBase):
    """Qdrant-backed vector store using the async client."""

    def __init__(self) -> None:
        from qdrant_client import AsyncQdrantClient

        settings = get_settings()
        self._client = AsyncQdrantClient(url=settings.QDRANT_URL)
        self._collection = settings.VECTOR_COLLECTION
        self._vector_size = settings.VECTOR_SIZE

    async def ensure_collection(self) -> None:
        from qdrant_client.models import (
            Distance,
            OptimizersConfigDiff,
            QuantizationConfig,
            ScalarQuantization,
            ScalarType,
            VectorParams,
        )

        collections = await self._client.get_collections()
        names = [c.name for c in collections.collections]
        if self._collection not in names:
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self._vector_size,
                    distance=Distance.COSINE,
                ),
                optimizers_config=OptimizersConfigDiff(default_segment_number=2),
                quantization_config=QuantizationConfig(
                    scalar=ScalarQuantization(
                        type=ScalarType.INT8,
                        always_ram=True,
                    ),
                ),
            )

    async def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> int:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=id_, vector=vec, payload=payload)
            for id_, vec, payload in zip(ids, vectors, payloads)
        ]
        await self._client.upsert(
            collection_name=self._collection,
            points=points,
        )
        return len(points)

    async def query(
        self,
        vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        query_filter = None
        if filters:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            ]
            query_filter = Filter(must=conditions)

        results = await self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        return [
            {"id": str(pt.id), "score": pt.score, "payload": pt.payload}
            for pt in results.points
        ]


class FAISSMockVectorStore(VectorStoreBase):
    """In-memory FAISS-backed vector store for testing.

    Uses IndexFlatIP (inner product) with L2-normalized vectors
    to simulate cosine similarity.
    """

    def __init__(self, vector_size: int | None = None) -> None:
        import faiss

        self._vector_size = vector_size or get_settings().VECTOR_SIZE
        self._index = faiss.IndexFlatIP(self._vector_size)
        self._ids: list[str] = []
        self._payloads: list[dict[str, Any]] = []

    async def ensure_collection(self) -> None:
        pass  # FAISS index is always ready

    async def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> int:
        arr = np.array(vectors, dtype=np.float32)
        # L2-normalize for cosine similarity via inner product
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        arr = arr / norms

        self._index.add(arr)
        self._ids.extend(ids)
        self._payloads.extend(payloads)
        return len(ids)

    async def query(
        self,
        vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if self._index.ntotal == 0:
            return []

        q = np.array([vector], dtype=np.float32)
        norms = np.linalg.norm(q, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        q = q / norms

        k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(q, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            payload = self._payloads[idx]
            if filters:
                if not all(payload.get(fk) == fv for fk, fv in filters.items()):
                    continue
            results.append({
                "id": self._ids[idx],
                "score": float(score),
                "payload": payload,
            })
        return results


def get_vectorstore(use_mock: bool = False) -> VectorStoreBase:
    """Factory that returns the appropriate vector store."""
    if use_mock:
        return FAISSMockVectorStore()
    return QdrantVectorStore()
