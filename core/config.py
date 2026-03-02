"""Application configuration via pydantic-settings."""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseModel):
    """Configuration for a single RAG agent focused on a market segment."""

    name: str
    strategy_name: str
    universe: list[str]
    news_sources: str
    qdrant_collection: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_ENV: str = "dev"

    # Database
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/quant"

    # Vector DB
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""  # required for Qdrant Cloud

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # News Ingestion
    NEWS_POLL_INTERVAL_SECONDS: int = 120
    NEWS_SOURCES: str = (
        "rss:https://feeds.finance.yahoo.com/rss/2.0/"
        "headline?s=%5EGSPC&region=US&lang=en-US"
    )
    MAX_DOCS_PER_POLL: int = 50
    DEDUP_CONTENT_HASH: str = "sha256"

    # Market Data
    MARKET_DATA_PROVIDER: str = "alpaca"
    ALPACA_API_KEY: str = ""
    ALPACA_API_SECRET: str = ""
    ALPACA_BASE_URL: str = "https://paper-api.alpaca.markets"
    MARKET_DATA_LOOKBACK_DAYS: int = 365
    BAR_TIMEFRAME: str = "1Day"

    # Embeddings & Vector DB
    EMBEDDINGS_PROVIDER: str = "mock"
    OPENAI_API_KEY: str = ""
    VECTOR_COLLECTION: str = "news"
    VECTOR_SIZE: int = 1536
    CHUNK_SIZE_CHARS: int = 1000
    CHUNK_OVERLAP_CHARS: int = 150

    # Sentiment
    SENTIMENT_PROVIDER: str = "finbert"

    # Risk & Execution
    RISK_MAX_GROSS_EXPOSURE: float = 1.0
    RISK_MAX_POSITION_PCT: float = 0.10
    RISK_MAX_DAILY_LOSS_PCT: float = 0.02
    RISK_MAX_TRADES_PER_HOUR: int = 30
    RISK_MAX_DATA_STALENESS_MINUTES: int = 30
    PAPER_INITIAL_CASH: float = 100_000
    PAPER_GUARD: bool = True
    TRADING_MODE: str = "paper"
    BROKER_PROVIDER: str = "internal"  # "internal" | "alpaca"

    # LLM (RAG Agent)
    LLM_PROVIDER: str = "anthropic"
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-4-6"

    # Strategy Agent
    STRATEGY_MIN_CONFIDENCE: float = 0.6
    STRATEGY_MAX_DIFF_FIELDS: int = 3
    STRATEGY_MAX_ACTIVATIONS_PER_DAY: int = 4
    STRATEGY_MIN_BACKTEST_DAYS: int = 252
    STRATEGY_APPROVED_UNIVERSE: str = "SPY,QQQ,AAPL,MSFT,AMZN,GOOGL,META,NVDA,BRK.B,JPM"
    PENDING_APPROVAL_AUTO_APPROVE_MINUTES: int = 0

    # Backtest cost model
    BACKTEST_COMMISSION_PER_TRADE: float = Field(default=1.0)
    BACKTEST_SLIPPAGE_BPS: float = Field(default=5.0)
    BACKTEST_SPREAD_BPS: float = Field(default=2.0)

    # Backtest activation thresholds
    BACKTEST_MIN_SHARPE: float = Field(default=0.5)
    BACKTEST_MAX_DRAWDOWN: float = Field(default=0.25)
    BACKTEST_MIN_WIN_RATE: float = Field(default=0.40)

    # Multi-agent
    AGENT_CONFIGS: str = "[]"

    @model_validator(mode="after")
    def _fix_database_url(self) -> "Settings":
        """Ensure DATABASE_URL uses the psycopg async driver prefix.

        Railway's Postgres plugin provides URLs starting with postgresql://
        or postgres://, but SQLAlchemy needs the +psycopg driver suffix.
        """
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            object.__setattr__(
                self, "DATABASE_URL",
                url.replace("postgresql://", "postgresql+psycopg://", 1),
            )
        elif url.startswith("postgres://"):
            object.__setattr__(
                self, "DATABASE_URL",
                url.replace("postgres://", "postgresql+psycopg://", 1),
            )
        return self

    @property
    def approved_universe_list(self) -> list[str]:
        """Parse STRATEGY_APPROVED_UNIVERSE CSV into a list."""
        return [t.strip() for t in self.STRATEGY_APPROVED_UNIVERSE.split(",") if t.strip()]

    @property
    def parsed_agent_configs(self) -> list[AgentConfig]:
        """Parse AGENT_CONFIGS JSON string into a list of AgentConfig."""
        raw = json.loads(self.AGENT_CONFIGS)
        return [AgentConfig.model_validate(item) for item in raw]


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Return the cached settings singleton. Hard-exits if TRADING_MODE != 'paper'."""
    global _settings
    if _settings is None:
        _settings = Settings()
        if _settings.TRADING_MODE != "paper":
            print(
                f"FATAL: TRADING_MODE={_settings.TRADING_MODE!r} is not 'paper'. "
                "Only paper trading is supported in v1. Exiting.",
                file=sys.stderr,
            )
            sys.exit(1)
    return _settings


def _reset_settings() -> None:
    """Reset the settings singleton. For use in tests only."""
    global _settings
    _settings = None


# Convenience alias
settings = get_settings()
