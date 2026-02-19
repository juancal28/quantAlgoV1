"""SQLAlchemy 2.x declarative models for all Postgres tables."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class NewsDocument(Base):
    __tablename__ = "news_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    # 'metadata' is reserved by SQLAlchemy, so we use metadata_ as the Python attr
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(Text, nullable=True)


class MarketBar(Base):
    __tablename__ = "market_bars"
    __table_args__ = (
        UniqueConstraint("ticker", "timeframe", "bar_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticker: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False)
    bar_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    open: Mapped[float] = mapped_column(Numeric, nullable=False)
    high: Mapped[float] = mapped_column(Numeric, nullable=False)
    low: Mapped[float] = mapped_column(Numeric, nullable=False)
    close: Mapped[float] = mapped_column(Numeric, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    backtest_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    audit_logs: Mapped[list[StrategyAuditLog]] = relationship(
        back_populates="strategy_version"
    )


class StrategyAuditLog(Base):
    __tablename__ = "strategy_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    strategy_name: Mapped[str] = mapped_column(Text, nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy_versions.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    before_definition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_definition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    backtest_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    llm_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    strategy_version: Mapped[StrategyVersion] = relationship(
        back_populates="audit_logs"
    )


class PnlSnapshot(Base):
    __tablename__ = "pnl_snapshots"
    __table_args__ = (
        UniqueConstraint("strategy_name", "snapshot_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Numeric, nullable=False)
    gross_exposure: Mapped[float] = mapped_column(Numeric, nullable=False)
    peak_pnl: Mapped[float] = mapped_column(Numeric, nullable=False)
    positions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_type: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
