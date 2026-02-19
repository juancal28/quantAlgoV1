"""MCP tool input/output schemas (Pydantic v2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --- ingest_latest_news ---

class IngestInput(BaseModel):
    max_items: int = Field(default=50, description="Max articles to fetch")


class IngestOutput(BaseModel):
    ingested: int
    doc_ids: list[str]


# --- embed_and_upsert_docs ---

class EmbedInput(BaseModel):
    doc_ids: list[str] = Field(description="Document IDs to embed and upsert")


class EmbedOutput(BaseModel):
    upserted_chunks: int


# --- score_sentiment ---

class SentimentInput(BaseModel):
    doc_ids: list[str] = Field(description="Document IDs to score")


class SentimentOutput(BaseModel):
    scored: int


# --- query_kb ---

class QueryInput(BaseModel):
    query: str = Field(description="Search query text")
    top_k: int = Field(default=10, description="Number of results to return")
    filters: dict[str, Any] | None = Field(default=None, description="Optional payload filters")


class QueryResultItem(BaseModel):
    doc_id: str
    title: str
    score: float
    snippet: str
    published_at: str
    source_url: str
    sentiment_score: float | None = None


class QueryOutput(BaseModel):
    results: list[QueryResultItem]
