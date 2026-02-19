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


# --- monitor_strategies ---

class StrategyOverviewInput(BaseModel):
    status: str | None = Field(default=None, description="Filter by status (pending_approval, active, archived)")
    limit: int = Field(default=50, description="Max strategies to return")


class StrategyOverviewItem(BaseModel):
    name: str
    version: int
    status: str
    created_at: str
    backtest_metrics: dict[str, Any] | None = None


class StrategyOverviewOutput(BaseModel):
    strategies: list[StrategyOverviewItem]


# --- monitor_runs ---

class RecentRunsInput(BaseModel):
    limit: int = Field(default=20, description="Max runs to return")


class RecentRunItem(BaseModel):
    id: str
    run_type: str
    started_at: str
    ended_at: str | None = None
    status: str
    details: dict[str, Any] | None = None


class RecentRunsOutput(BaseModel):
    runs: list[RecentRunItem]


# --- monitor_pnl ---

class PnlSummaryInput(BaseModel):
    strategy_name: str = Field(description="Strategy to query PnL for")
    days: int = Field(default=30, description="Number of days of PnL history")


class PnlSummaryItem(BaseModel):
    date: str
    realized_pnl: float
    unrealized_pnl: float
    gross_exposure: float
    peak_pnl: float
    positions: dict[str, Any] | None = None


class PnlSummaryOutput(BaseModel):
    snapshots: list[PnlSummaryItem]


# --- monitor_health ---

class SystemHealthInput(BaseModel):
    pass  # No inputs required


class SystemHealthOutput(BaseModel):
    trading_mode: str
    paper_guard: bool
    market_open: bool
    last_ingest_run: dict[str, Any] | None = None
    news_count_last_2h: int
    strategy_counts: dict[str, int]
    services: dict[str, str]


# --- monitor_news ---

class RecentNewsInput(BaseModel):
    minutes: int = Field(default=120, description="Time window in minutes")
    limit: int = Field(default=20, description="Max articles to return")


class RecentNewsItem(BaseModel):
    id: str
    title: str
    source: str
    published_at: str
    sentiment_score: float | None = None
    sentiment_label: str | None = None
    tickers: list[str]


class RecentNewsOutput(BaseModel):
    articles: list[RecentNewsItem]


# --- propose_strategy_update ---

class ProposeStrategyInput(BaseModel):
    strategy_name: str = Field(description="Strategy to propose update for")
    recent_minutes: int = Field(default=240, description="Lookback window in minutes")


class ProposeStrategyOutput(BaseModel):
    proposal: dict[str, Any]


# --- validate_strategy ---

class ValidateStrategyInput(BaseModel):
    definition_json: dict[str, Any] = Field(description="Strategy definition to validate")


class ValidateStrategyOutput(BaseModel):
    valid: bool
    errors: list[str]


# --- submit_strategy_for_approval ---

class SubmitStrategyInput(BaseModel):
    strategy_name: str = Field(description="Strategy name")
    definition_json: dict[str, Any] = Field(description="Strategy definition")
    reason: str = Field(description="Reason for submission")
    backtest_metrics: dict[str, Any] | None = Field(default=None, description="Backtest results")


class SubmitStrategyOutput(BaseModel):
    strategy_version_id: str
    status: str
