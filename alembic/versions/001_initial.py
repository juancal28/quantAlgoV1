"""Initial schema — all 6 tables.

Revision ID: 001
Revises:
Create Date: 2026-02-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- news_documents ---
    op.create_table(
        "news_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("sentiment_label", sa.Text(), nullable=True),
    )
    op.create_index("ix_news_documents_source_url", "news_documents", ["source_url"], unique=True)
    op.create_index(
        "ix_news_documents_content_hash", "news_documents", ["content_hash"], unique=True
    )

    # --- market_bars ---
    op.create_table(
        "market_bars",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("timeframe", sa.Text(), nullable=False),
        sa.Column("bar_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(), nullable=False),
        sa.Column("high", sa.Numeric(), nullable=False),
        sa.Column("low", sa.Numeric(), nullable=False),
        sa.Column("close", sa.Numeric(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("ticker", "timeframe", "bar_time"),
    )
    op.create_index("ix_market_bars_ticker", "market_bars", ["ticker"])

    # --- strategy_versions ---
    op.create_table(
        "strategy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("backtest_metrics", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_strategy_versions_name", "strategy_versions", ["name"])

    # --- strategy_audit_log (FK to strategy_versions) ---
    op.create_table(
        "strategy_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("strategy_name", sa.Text(), nullable=False),
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategy_versions.id"),
            nullable=False,
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("before_definition", postgresql.JSONB(), nullable=True),
        sa.Column("after_definition", postgresql.JSONB(), nullable=True),
        sa.Column("backtest_metrics", postgresql.JSONB(), nullable=True),
        sa.Column("llm_rationale", sa.Text(), nullable=True),
        sa.Column("diff_fields", postgresql.JSONB(), nullable=True),
    )

    # --- pnl_snapshots ---
    op.create_table(
        "pnl_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("strategy_name", sa.Text(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(), nullable=False),
        sa.Column("gross_exposure", sa.Numeric(), nullable=False),
        sa.Column("peak_pnl", sa.Numeric(), nullable=False),
        sa.Column("positions", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("strategy_name", "snapshot_date"),
    )
    op.create_index("ix_pnl_snapshots_strategy_name", "pnl_snapshots", ["strategy_name"])

    # --- runs ---
    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_type", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    # Drop in FK-safe order: audit_log references strategy_versions
    op.drop_table("runs")
    op.drop_table("pnl_snapshots")
    op.drop_table("strategy_audit_log")
    op.drop_table("strategy_versions")
    op.drop_table("market_bars")
    op.drop_table("news_documents")
