"""Read-only monitoring MCP tools for operator visibility."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.mcp_server.schemas import (
    PnlSummaryInput,
    PnlSummaryItem,
    PnlSummaryOutput,
    RecentNewsInput,
    RecentNewsItem,
    RecentNewsOutput,
    RecentRunItem,
    RecentRunsInput,
    RecentRunsOutput,
    StrategyOverviewInput,
    StrategyOverviewItem,
    StrategyOverviewOutput,
    SystemHealthInput,
    SystemHealthOutput,
)
from core.config import get_settings
from core.logging import get_logger
from core.storage.repos import news_repo, pnl_repo, run_repo, strategy_repo

logger = get_logger(__name__)


async def get_strategy_overview(
    session: AsyncSession,
    params: StrategyOverviewInput,
) -> StrategyOverviewOutput:
    """Return a summary of all strategies, optionally filtered by status."""
    rows = await strategy_repo.get_all_strategies(
        session, status=params.status, limit=params.limit
    )
    items = [
        StrategyOverviewItem(
            name=sv.name,
            version=sv.version,
            status=sv.status,
            created_at=sv.created_at.isoformat() if sv.created_at else "",
            backtest_metrics=sv.backtest_metrics,
        )
        for sv in rows
    ]
    return StrategyOverviewOutput(strategies=items)


async def get_recent_runs(
    session: AsyncSession,
    params: RecentRunsInput,
) -> RecentRunsOutput:
    """Return recent pipeline runs."""
    rows = await run_repo.get_recent(session, limit=params.limit)
    items = [
        RecentRunItem(
            id=str(r.id),
            run_type=r.run_type,
            started_at=r.started_at.isoformat() if r.started_at else "",
            ended_at=r.ended_at.isoformat() if r.ended_at else None,
            status=r.status,
            details=r.details,
        )
        for r in rows
    ]
    return RecentRunsOutput(runs=items)


async def get_pnl_summary(
    session: AsyncSession,
    params: PnlSummaryInput,
) -> PnlSummaryOutput:
    """Return PnL snapshots for a strategy."""
    rows = await pnl_repo.get_daily_snapshots(
        session, strategy_name=params.strategy_name, limit=params.days
    )
    items = [
        PnlSummaryItem(
            date=str(s.snapshot_date),
            realized_pnl=float(s.realized_pnl),
            unrealized_pnl=float(s.unrealized_pnl),
            gross_exposure=float(s.gross_exposure),
            peak_pnl=float(s.peak_pnl),
            positions=s.positions,
        )
        for s in rows
    ]
    return PnlSummaryOutput(snapshots=items)


async def get_system_health(
    session: AsyncSession,
    params: SystemHealthInput,
) -> SystemHealthOutput:
    """Return overall system health: config, market status, last ingest, counts."""
    settings = get_settings()

    # Market hours check
    try:
        from core.timeutils import is_market_open
        market_open = is_market_open()
    except Exception:
        market_open = False

    # Last ingest run
    last_ingest = await run_repo.get_latest_by_type(session, "ingest")
    last_ingest_info = None
    if last_ingest is not None:
        last_ingest_info = {
            "id": str(last_ingest.id),
            "started_at": last_ingest.started_at.isoformat() if last_ingest.started_at else "",
            "status": last_ingest.status,
        }

    # News count
    news_count = await news_repo.count_recent(session, minutes=120)

    # Strategy counts by status
    all_strategies = await strategy_repo.get_all_strategies(session, limit=1000)
    counts: dict[str, int] = {}
    for sv in all_strategies:
        counts[sv.status] = counts.get(sv.status, 0) + 1

    # Service connectivity (basic checks)
    services: dict[str, str] = {"postgres": "ok"}

    try:
        from core.kb.vectorstore import QdrantVectorStore
        qdrant = QdrantVectorStore()
        await qdrant._client.get_collections()
        services["qdrant"] = "ok"
    except Exception:
        services["qdrant"] = "unavailable"

    return SystemHealthOutput(
        trading_mode=settings.TRADING_MODE,
        paper_guard=settings.PAPER_GUARD,
        market_open=market_open,
        last_ingest_run=last_ingest_info,
        news_count_last_2h=news_count,
        strategy_counts=counts,
        services=services,
    )


async def get_recent_news_summary(
    session: AsyncSession,
    params: RecentNewsInput,
) -> RecentNewsOutput:
    """Return recent news articles with sentiment and tickers."""
    rows = await news_repo.get_recent(
        session, minutes=params.minutes, limit=params.limit
    )
    items = [
        RecentNewsItem(
            id=str(doc.id),
            title=doc.title,
            source=doc.source,
            published_at=doc.published_at.isoformat() if doc.published_at else "",
            sentiment_score=doc.sentiment_score,
            sentiment_label=doc.sentiment_label,
            tickers=(doc.metadata_ or {}).get("tickers", []),
        )
        for doc in rows
    ]
    return RecentNewsOutput(articles=items)
