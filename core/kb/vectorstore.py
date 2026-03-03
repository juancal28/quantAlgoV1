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

    @abc.abstractmethod
    async def delete_by_doc_ids(self, doc_ids: list[str]) -> int:
        """Delete all points whose payload ``doc_id`` is in *doc_ids*. Returns count deleted."""


class QdrantVectorStore(VectorStoreBase):
    """Qdrant-backed vector store using the async client."""

    def __init__(self, collection_name: str | None = None) -> None:
        from qdrant_client import AsyncQdrantClient

        settings = get_settings()
        self._client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )
        self._collection = collection_name or settings.VECTOR_COLLECTION
        self._vector_size = settings.VECTOR_SIZE

    async def ensure_collection(self) -> None:
        from qdrant_client.models import (
            Distance,
            OptimizersConfigDiff,
            ScalarQuantization,
            ScalarQuantizationConfig,
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
                quantization_config=ScalarQuantization(
                    scalar=ScalarQuantizationConfig(
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


    async def delete_by_doc_ids(self, doc_ids: list[str]) -> int:
        """Delete all points whose payload ``doc_id`` matches any of *doc_ids*."""
        if not doc_ids:
            return 0
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            MatchAny,
            PointsSelector,
            FilterSelector,
        )

        await self._client.delete(
            collection_name=self._collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="doc_id", match=MatchAny(any=doc_ids))
                    ]
                )
            ),
        )
        # Qdrant delete doesn't return a count; return len(doc_ids) as upper bound
        return len(doc_ids)


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


    async def delete_by_doc_ids(self, doc_ids: list[str]) -> int:
        """Remove all vectors whose payload ``doc_id`` is in *doc_ids*."""
        if not doc_ids:
            return 0
        import faiss

        target_set = set(doc_ids)
        keep_indices = [
            i
            for i, p in enumerate(self._payloads)
            if p.get("doc_id") not in target_set
        ]
        deleted = len(self._payloads) - len(keep_indices)

        if deleted == 0:
            return 0

        # Rebuild index from kept vectors
        if keep_indices:
            kept_vectors = np.array(
                [self._index.reconstruct(int(i)) for i in keep_indices],
                dtype=np.float32,
            )
            self._ids = [self._ids[i] for i in keep_indices]
            self._payloads = [self._payloads[i] for i in keep_indices]
            self._index = faiss.IndexFlatIP(self._vector_size)
            self._index.add(kept_vectors)
        else:
            self._ids = []
            self._payloads = []
            self._index = faiss.IndexFlatIP(self._vector_size)

        return deleted


def get_vectorstore(
    use_mock: bool = False, collection_name: str | None = None
) -> VectorStoreBase:
    """Factory that returns the appropriate vector store."""
    if use_mock:
        return FAISSMockVectorStore()
    return QdrantVectorStore(collection_name=collection_name)
