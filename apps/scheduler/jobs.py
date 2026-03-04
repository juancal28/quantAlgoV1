"""Celery scheduled jobs."""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

# Windows async policy — required for psycopg async on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from apps.scheduler.worker import celery_app
from core.config import get_settings
from core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

PAUSE_KEY = "scheduler:paused"
AUTONOMOUS_KEY = "autonomous:enabled"


def _is_scheduler_paused() -> bool:
    """Check Redis for the global scheduler pause flag."""
    r = _get_redis_client()
    return bool(r.exists(PAUSE_KEY))


def _is_autonomous_mode() -> bool:
    """Check Redis for the autonomous mode flag."""
    r = _get_redis_client()
    return bool(r.exists(AUTONOMOUS_KEY))


# ---------------------------------------------------------------------------
# Redis singleton locks — prevent overlapping task executions
# ---------------------------------------------------------------------------

def _get_redis_client():
    """Return a Redis client from the configured REDIS_URL."""
    import redis

    settings = get_settings()
    return redis.Redis.from_url(settings.REDIS_URL)


def _acquire_singleton_lock(name: str, ttl: int) -> bool:
    """Try to acquire a Redis lock via SET NX EX. Returns True if acquired."""
    r = _get_redis_client()
    return bool(r.set(f"lock:{name}", "1", nx=True, ex=ttl))


def _release_singleton_lock(name: str) -> None:
    """Release a Redis singleton lock."""
    r = _get_redis_client()
    r.delete(f"lock:{name}")


@celery_app.task(
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    name="apps.scheduler.jobs.run_news_cycle",
)
def run_news_cycle(
    self, run_id: str | None = None, agent_name: str | None = None
) -> dict:
    """Execute the full news cycle pipeline.

    Uses a Redis singleton lock to prevent overlapping runs. If a previous
    cycle is still in progress, this invocation is skipped.

    Steps:
    1. ingest_latest_news
    2. embed_and_upsert_docs
    3. score_sentiment
    4. propose_strategy_update
    5. validate_strategy
    6. score_proposal_quality
    7. submit_strategy_for_approval (if quality passes)

    Args:
        run_id: Optional pre-created run ID.
        agent_name: Optional agent name from AGENT_CONFIGS. When provided,
            uses the agent's feeds, Qdrant collection, and strategy name.
    """
    if _is_scheduler_paused():
        logger.info("Scheduler paused — skipping news_cycle")
        return {"skipped": True, "reason": "scheduler_paused"}

    settings = get_settings()
    lock_name = f"news_cycle:{agent_name or 'default'}"
    lock_ttl = settings.NEWS_POLL_INTERVAL_SECONDS * 2

    if not _acquire_singleton_lock(lock_name, lock_ttl):
        logger.info(
            "Skipping news_cycle — previous run still in progress (agent=%s)",
            agent_name or "default",
        )
        return {"skipped": True, "reason": "lock_held"}

    try:
        return asyncio.run(_run_news_cycle_async(run_id, agent_name=agent_name))
    finally:
        _release_singleton_lock(lock_name)


async def _run_news_cycle_async(
    run_id: str | None = None,
    _session: AsyncSession | None = None,
    agent_name: str | None = None,
) -> dict:
    """Async implementation of the news cycle pipeline.

    Args:
        run_id: Optional pre-created run ID to associate with this cycle.
        _session: Optional session for testing. If None, creates one via get_session().
        agent_name: Optional agent name. When set, uses the agent's feeds,
            Qdrant collection, and strategy name from AGENT_CONFIGS.
    """
    from apps.mcp_server.schemas import (
        EmbedInput,
        IngestInput,
        ProposeStrategyInput,
        SentimentInput,
        SubmitStrategyInput,
        ValidateStrategyInput,
    )
    from apps.mcp_server.tools.ingest import ingest_latest_news
    from apps.mcp_server.tools.kb import embed_and_upsert_docs
    from apps.mcp_server.tools.sentiment import score_sentiment
    from apps.mcp_server.tools.strategy import (
        propose_strategy,
        submit_strategy,
        validate_strategy_tool,
    )
    from core.agent.quality_scorer import score_proposal_quality
    from core.ingestion.fetchers.rss import RSSFetcher
    from core.kb.vectorstore import get_vectorstore
    from core.storage.repos import run_repo

    settings = get_settings()
    details: dict = {}

    # Resolve agent config
    agent_cfg = None
    if agent_name:
        for cfg in settings.parsed_agent_configs:
            if cfg.name == agent_name:
                agent_cfg = cfg
                break
        if agent_cfg is None:
            raise ValueError(f"Agent '{agent_name}' not found in AGENT_CONFIGS")
        details["agent_name"] = agent_name

    # Determine agent-specific or global values
    strategy_name = agent_cfg.strategy_name if agent_cfg else "sentiment_momentum_v1"
    feed_urls: list[str] | None = None
    if agent_cfg:
        feed_urls = RSSFetcher._parse_feed_urls(agent_cfg.news_sources)

    # Build agent-specific vectorstore (or default)
    store = None
    if agent_cfg:
        store = get_vectorstore(collection_name=agent_cfg.qdrant_collection)

    async def _execute(session: AsyncSession) -> dict:
        nonlocal details
        run = None
        cycle_start = time.monotonic()
        try:
            # If a run_id was provided, look it up; otherwise create one
            if run_id:
                run = await run_repo.get_by_id(session, uuid.UUID(run_id))
            else:
                run = await run_repo.create_run(session, run_type="ingest")
                await session.flush()

            # 1. Ingest latest news
            t0 = time.monotonic()
            ingest_result = await ingest_latest_news(
                session,
                IngestInput(
                    max_items=settings.MAX_DOCS_PER_POLL,
                    feed_urls=feed_urls,
                ),
            )
            details["ingested"] = ingest_result.ingested
            details["doc_ids"] = ingest_result.doc_ids
            details["timing_ingest_s"] = round(time.monotonic() - t0, 2)
            logger.info(
                "Step 1/7 ingest: %d docs in %.1fs",
                ingest_result.ingested, details["timing_ingest_s"],
            )

            if ingest_result.ingested == 0:
                logger.info("No new docs ingested — skipping embed/sentiment, proceeding to proposal")
                details["skipped_embed_sentiment"] = True
            else:
                # 2. Embed and upsert (with agent-specific store if set)
                t0 = time.monotonic()
                embed_result = await embed_and_upsert_docs(
                    session, EmbedInput(doc_ids=ingest_result.doc_ids), store=store
                )
                details["upserted_chunks"] = embed_result.upserted_chunks
                details["timing_embed_s"] = round(time.monotonic() - t0, 2)
                logger.info(
                    "Step 2/7 embed: %d chunks in %.1fs",
                    embed_result.upserted_chunks, details["timing_embed_s"],
                )

                # 3. Score sentiment
                t0 = time.monotonic()
                sentiment_result = await score_sentiment(
                    session, SentimentInput(doc_ids=ingest_result.doc_ids)
                )
                details["scored"] = sentiment_result.scored
                details["timing_sentiment_s"] = round(time.monotonic() - t0, 2)
                logger.info(
                    "Step 3/7 sentiment: %d scored in %.1fs",
                    sentiment_result.scored, details["timing_sentiment_s"],
                )

            # 4. Propose strategy update (with agent-specific store if set)
            # Use a wider window (4 hours) so KB has enough context even
            # when no new docs were ingested this cycle.
            t0 = time.monotonic()
            proposal_result = await propose_strategy(
                session,
                ProposeStrategyInput(
                    strategy_name=strategy_name,
                    recent_minutes=240,
                ),
                store=store,
            )
            proposal = proposal_result.proposal
            confidence = proposal.get("confidence", 0.0)
            details["confidence"] = confidence
            details["timing_propose_s"] = round(time.monotonic() - t0, 2)
            logger.info(
                "Step 4/7 propose: confidence=%.2f in %.1fs",
                confidence, details["timing_propose_s"],
            )

            if confidence < settings.STRATEGY_MIN_CONFIDENCE:
                details["early_exit"] = "low_confidence"
                details["timing_total_s"] = round(time.monotonic() - cycle_start, 2)
                logger.warning(
                    "Pipeline exit: low_confidence (%.2f < %.2f) after %.1fs total",
                    confidence, settings.STRATEGY_MIN_CONFIDENCE, details["timing_total_s"],
                )
                await run_repo.complete_run(session, run.id, status="ok", details=details)
                await session.flush()
                return details

            # 5. Validate strategy
            t0 = time.monotonic()
            new_definition = proposal.get("new_definition", {})
            validation = await validate_strategy_tool(
                ValidateStrategyInput(definition_json=new_definition)
            )
            details["valid"] = validation.valid
            details["validation_errors"] = validation.errors
            details["timing_validate_s"] = round(time.monotonic() - t0, 2)
            logger.info(
                "Step 5/7 validate: valid=%s in %.1fs",
                validation.valid, details["timing_validate_s"],
            )

            if not validation.valid:
                details["early_exit"] = "validation_failed"
                details["timing_total_s"] = round(time.monotonic() - cycle_start, 2)
                logger.warning(
                    "Pipeline exit: validation_failed (%s) after %.1fs total",
                    validation.errors, details["timing_total_s"],
                )
                await run_repo.complete_run(session, run.id, status="ok", details=details)
                await session.flush()
                return details

            # 6. Score proposal quality
            t0 = time.monotonic()
            quality_result = await score_proposal_quality(
                session, proposal, new_definition,
            )
            details["quality_score"] = quality_result.composite
            details["quality_passed"] = quality_result.passed
            details["quality_dimensions"] = {
                dim.name: {"score": round(dim.score, 4), "detail": dim.detail}
                for dim in quality_result.dimensions
            }
            details["timing_quality_s"] = round(time.monotonic() - t0, 2)
            logger.info(
                "Step 6/7 quality: composite=%.3f passed=%s in %.1fs",
                quality_result.composite, quality_result.passed, details["timing_quality_s"],
            )

            # 7. Submit for approval if quality passes
            if quality_result.passed:
                t0 = time.monotonic()
                submit_result = await submit_strategy(
                    session,
                    SubmitStrategyInput(
                        strategy_name=new_definition.get("name", strategy_name),
                        definition_json=new_definition,
                        reason=proposal.get("rationale", "Agent-proposed update"),
                        backtest_metrics={
                            "quality_score": quality_result.to_dict(),
                        },
                    ),
                )
                details["submitted_version_id"] = submit_result.strategy_version_id
                details["timing_submit_s"] = round(time.monotonic() - t0, 2)
                logger.info(
                    "Step 7/7 submit: version_id=%s in %.1fs",
                    submit_result.strategy_version_id, details["timing_submit_s"],
                )
            else:
                details["early_exit"] = "quality_failed"
                logger.warning(
                    "Pipeline exit: quality_failed (composite=%.3f < %.3f)",
                    quality_result.composite, settings.QUALITY_MIN_COMPOSITE_SCORE,
                )

            details["timing_total_s"] = round(time.monotonic() - cycle_start, 2)
            logger.info("News cycle completed in %.1fs", details["timing_total_s"])
            await run_repo.complete_run(session, run.id, status="ok", details=details)
            await session.flush()

        except Exception as exc:
            details["timing_total_s"] = round(time.monotonic() - cycle_start, 2)
            logger.error("News cycle failed after %.1fs: %s", details["timing_total_s"], exc, exc_info=True)
            details["error"] = str(exc)
            if run:
                await run_repo.complete_run(session, run.id, status="fail", details=details)
                await session.flush()
            raise

        return details

    if _session is not None:
        return await _execute(_session)

    from core.storage.db import get_session

    async for session in get_session():
        result = await _execute(session)
        await session.commit()
        return result

    return details


@celery_app.task(
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    name="apps.scheduler.jobs.run_paper_trade_tick_all",
)
def run_paper_trade_tick_all(self) -> dict:
    """Execute paper trade tick for all active strategies.

    Uses a Redis singleton lock to prevent overlapping ticks.
    """
    if _is_scheduler_paused():
        logger.info("Scheduler paused — skipping paper_trade_tick")
        return {"skipped": True, "reason": "scheduler_paused"}

    lock_name = "paper_trade_tick"
    lock_ttl = 120

    if not _acquire_singleton_lock(lock_name, lock_ttl):
        logger.info("Skipping paper_trade_tick — previous tick still in progress")
        return {"skipped": True, "reason": "lock_held"}

    try:
        return asyncio.run(_run_paper_trade_tick_all_async())
    finally:
        _release_singleton_lock(lock_name)


async def _run_paper_trade_tick_all_async(
    _session: AsyncSession | None = None,
) -> dict:
    """Async implementation: tick all active strategies.

    Args:
        _session: Optional session for testing. If None, creates one via get_session().
    """
    from apps.mcp_server.schemas import PaperTradeTickInput
    from apps.mcp_server.tools.execution import paper_trade_tick
    from core.storage.repos import strategy_repo

    results: dict = {"ticked": [], "market_open": True}

    async def _execute(session: AsyncSession) -> dict:
        active_versions = await strategy_repo.get_all_strategies(
            session, status="active"
        )

        if not active_versions:
            logger.info("No active strategies to tick")
            results["ticked"] = []
            return results

        # Deduplicate by strategy name
        seen_names: set[str] = set()
        unique_names: list[str] = []
        for v in active_versions:
            if v.name not in seen_names:
                seen_names.add(v.name)
                unique_names.append(v.name)

        for name in unique_names:
            tick_result = await paper_trade_tick(
                session, PaperTradeTickInput(strategy_name=name)
            )
            if not tick_result.market_open:
                logger.info("Market closed, stopping tick loop")
                results["market_open"] = False
                return results

            results["ticked"].append(name)

        return results

    if _session is not None:
        return await _execute(_session)

    from core.storage.db import get_session

    async for session in get_session():
        result = await _execute(session)
        await session.commit()
        return result

    return results


# ---------------------------------------------------------------------------
# Market data ingestion task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    name="apps.scheduler.jobs.run_market_data_ingest",
)
def run_market_data_ingest(self) -> dict:
    """Fetch and store market bars for the approved universe.

    Runs daily. Fetches enough history to cover both backtest windows
    (in-sample + out-of-sample).
    """
    if _is_scheduler_paused():
        logger.info("Scheduler paused — skipping market_data_ingest")
        return {"skipped": True, "reason": "scheduler_paused"}

    lock_name = "market_data_ingest"
    lock_ttl = 600

    if not _acquire_singleton_lock(lock_name, lock_ttl):
        logger.info("Skipping market_data_ingest — previous run still in progress")
        return {"skipped": True, "reason": "lock_held"}

    try:
        return asyncio.run(_run_market_data_ingest_async())
    finally:
        _release_singleton_lock(lock_name)


async def _run_market_data_ingest_async(
    _session: "AsyncSession | None" = None,
) -> dict:
    """Async implementation: fetch and store market bars."""
    from core.ingestion.fetchers.market_data import fetch_and_store_bars

    settings = get_settings()
    tickers = settings.approved_universe_list

    # Enough lookback for IS + OOS windows with buffer
    backtest_days = settings.STRATEGY_MIN_BACKTEST_DAYS
    is_calendar_days = int(backtest_days * 365 / 252)
    lookback_days = is_calendar_days + 90 + 30

    async def _execute(session: "AsyncSession") -> dict:
        count = await fetch_and_store_bars(
            session,
            tickers=tickers,
            lookback_days=lookback_days,
        )
        logger.info(
            "Market data ingest: %d bars for %d tickers (lookback=%dd)",
            count, len(tickers), lookback_days,
        )
        return {"bars_upserted": count, "tickers": tickers, "lookback_days": lookback_days}

    if _session is not None:
        return await _execute(_session)

    from core.storage.db import get_session

    async for session in get_session():
        result = await _execute(session)
        await session.commit()
        return result

    return {"bars_upserted": 0, "tickers": tickers, "lookback_days": lookback_days}


# ---------------------------------------------------------------------------
# Auto-approve task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    name="apps.scheduler.jobs.run_auto_approve",
)
def run_auto_approve(self) -> dict:
    """Auto-approve pending strategies.

    In autonomous mode (Redis flag): approve immediately, no age gate.
    Otherwise: approve after PENDING_APPROVAL_AUTO_APPROVE_MINUTES.
    """
    if _is_scheduler_paused():
        logger.info("Scheduler paused — skipping auto_approve")
        return {"skipped": True, "reason": "scheduler_paused"}

    autonomous = _is_autonomous_mode()

    settings = get_settings()
    if not autonomous and settings.PENDING_APPROVAL_AUTO_APPROVE_MINUTES <= 0:
        return {"skipped": True, "reason": "auto_approve_disabled"}
    return asyncio.run(_run_auto_approve_async(autonomous=autonomous))


async def _run_auto_approve_async(
    _session: "AsyncSession | None" = None,
    autonomous: bool = False,
) -> dict:
    """Async implementation: approve pending strategies.

    Args:
        _session: Optional session for testing.
        autonomous: If True, approve immediately (no age gate).
    """
    from core.agent.approval import approve_strategy
    from core.storage.repos import strategy_repo

    settings = get_settings()
    threshold_minutes = settings.PENDING_APPROVAL_AUTO_APPROVE_MINUTES
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)

    approved: list[str] = []
    errors: list[str] = []

    async def _execute(session: "AsyncSession") -> dict:
        pending = await strategy_repo.get_all_strategies(
            session, status="pending_approval"
        )

        for version in pending:
            # In autonomous mode, skip the age gate — approve immediately
            if not autonomous:
                if version.created_at.tzinfo is None:
                    created = version.created_at.replace(tzinfo=timezone.utc)
                else:
                    created = version.created_at
                if created > cutoff:
                    continue

            approved_by = "autonomous" if autonomous else "auto"
            try:
                await approve_strategy(
                    session,
                    strategy_name=version.name,
                    version_id=str(version.id),
                    approved_by=approved_by,
                )
                approved.append(f"{version.name}@v{version.version}")
                logger.info(
                    "Auto-approved strategy %s version %s (autonomous=%s)",
                    version.name,
                    version.version,
                    autonomous,
                )
            except ValueError as exc:
                errors.append(f"{version.name}@v{version.version}: {exc}")
                logger.warning(
                    "Auto-approve failed for %s v%s: %s",
                    version.name,
                    version.version,
                    exc,
                )

        return {"approved": approved, "errors": errors, "autonomous": autonomous}

    if _session is not None:
        return await _execute(_session)

    from core.storage.db import get_session

    async for session in get_session():
        result = await _execute(session)
        await session.commit()
        return result

    return {"approved": approved, "errors": errors}


# ---------------------------------------------------------------------------
# Strategy expiry task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    name="apps.scheduler.jobs.run_expire_strategies",
)
def run_expire_strategies(self) -> dict:
    """Archive active strategies that have exceeded STRATEGY_MAX_AGE_HOURS."""
    if _is_scheduler_paused():
        logger.info("Scheduler paused — skipping expire_strategies")
        return {"skipped": True, "reason": "scheduler_paused"}

    settings = get_settings()
    if settings.STRATEGY_MAX_AGE_HOURS <= 0:
        return {"skipped": True, "reason": "expiry_disabled"}
    return asyncio.run(_run_expire_strategies_async())


async def _run_expire_strategies_async(
    _session: "AsyncSession | None" = None,
) -> dict:
    """Async implementation: expire active strategies older than the configured TTL."""
    from core.agent.approval import deactivate_strategy
    from core.storage.repos import strategy_repo

    settings = get_settings()
    max_age_hours = settings.STRATEGY_MAX_AGE_HOURS

    archived: list[str] = []
    errors: list[str] = []

    async def _execute(session: "AsyncSession") -> dict:
        expired = await strategy_repo.get_expired_active_strategies(
            session, max_age_hours
        )

        for version in expired:
            try:
                await deactivate_strategy(
                    session,
                    strategy_name=version.name,
                    reason="TTL expired",
                    trigger="scheduler",
                )
                archived.append(f"{version.name}@v{version.version}")
                logger.info(
                    "Expired strategy %s version %s (TTL=%dh)",
                    version.name,
                    version.version,
                    max_age_hours,
                )
            except ValueError as exc:
                errors.append(f"{version.name}@v{version.version}: {exc}")
                logger.warning(
                    "Expire failed for %s v%s: %s",
                    version.name,
                    version.version,
                    exc,
                )

        return {"archived": archived, "errors": errors}

    if _session is not None:
        return await _execute(_session)

    from core.storage.db import get_session

    async for session in get_session():
        result = await _execute(session)
        await session.commit()
        return result

    return {"archived": archived, "errors": errors}


# ---------------------------------------------------------------------------
# News cleanup task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    name="apps.scheduler.jobs.run_news_cleanup",
)
def run_news_cleanup(self) -> dict:
    """Delete news documents older than NEWS_RETENTION_DAYS from Postgres and Qdrant."""
    if _is_scheduler_paused():
        logger.info("Scheduler paused — skipping news_cleanup")
        return {"skipped": True, "reason": "scheduler_paused"}

    settings = get_settings()
    if settings.NEWS_RETENTION_DAYS <= 0:
        return {"skipped": True, "reason": "news_cleanup_disabled"}
    return asyncio.run(_run_news_cleanup_async())


async def _run_news_cleanup_async(
    _session: "AsyncSession | None" = None,
) -> dict:
    """Async implementation: delete old news documents from Postgres and Qdrant."""
    from core.kb.vectorstore import get_vectorstore
    from core.storage.repos import news_repo

    settings = get_settings()
    retention_days = settings.NEWS_RETENTION_DAYS

    total_deleted = 0
    total_qdrant_deleted = 0
    errors: list[str] = []

    async def _execute(session: "AsyncSession") -> dict:
        nonlocal total_deleted, total_qdrant_deleted

        while True:
            old_docs = await news_repo.get_old_documents(
                session, days=retention_days, limit=500
            )
            if not old_docs:
                break

            doc_ids = [d.id for d in old_docs]
            doc_id_strs = [str(d.id) for d in old_docs]

            # Delete from Qdrant first (best effort)
            try:
                store = get_vectorstore(
                    collection_name=settings.VECTOR_COLLECTION
                )
                qdrant_deleted = await store.delete_by_doc_ids(doc_id_strs)
                total_qdrant_deleted += qdrant_deleted
            except Exception as exc:
                errors.append(f"qdrant_delete: {exc}")
                logger.warning("Qdrant delete failed: %s", exc)

            # Delete from Postgres
            deleted = await news_repo.delete_by_ids(session, doc_ids)
            total_deleted += deleted

        return {
            "deleted": total_deleted,
            "qdrant_deleted": total_qdrant_deleted,
            "errors": errors,
        }

    if _session is not None:
        return await _execute(_session)

    from core.storage.db import get_session

    async for session in get_session():
        result = await _execute(session)
        await session.commit()
        return result

    return {"deleted": 0, "qdrant_deleted": 0, "errors": errors}


# ---------------------------------------------------------------------------
# ML dependency update task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=600,
    name="apps.scheduler.jobs.run_ml_deps_update",
)
def run_ml_deps_update(self) -> dict:
    """Check for and install ML dependency updates on the persistent volume.

    Runs daily. Updates torch, transformers, and the FinBERT model if newer
    versions are available. Packages are installed to ML_CACHE_DIR/packages/
    so the update is picked up on next service restart.
    """
    if _is_scheduler_paused():
        logger.info("Scheduler paused — skipping ml_deps_update")
        return {"skipped": True, "reason": "scheduler_paused"}

    settings = get_settings()
    if settings.SENTIMENT_PROVIDER.lower() != "finbert":
        return {"skipped": True, "reason": "sentiment_provider_not_finbert"}

    import os
    import subprocess
    import sys

    ml_cache_dir = settings.ML_CACHE_DIR
    packages_dir = os.path.join(ml_cache_dir, "packages")
    hf_cache_dir = os.path.join(ml_cache_dir, "huggingface")

    if not os.path.isdir(packages_dir):
        logger.warning("ML packages dir %s not found — skipping update", packages_dir)
        return {"skipped": True, "reason": "packages_dir_missing"}

    results: dict = {"updated": [], "errors": []}

    # Update torch + transformers (pip only downloads if newer version exists)
    for pkg, extra_args in [
        ("torch", ["--index-url", "https://download.pytorch.org/whl/cpu"]),
        ("transformers", []),
    ]:
        try:
            cmd = [
                sys.executable, "-m", "pip", "install", "--upgrade",
                "--target", packages_dir, pkg,
            ] + extra_args
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
            if "already satisfied" not in output.lower():
                results["updated"].append(pkg)
                logger.info("Updated %s on volume", pkg)
            else:
                logger.info("%s already up to date", pkg)
        except subprocess.CalledProcessError as exc:
            results["errors"].append(f"{pkg}: {exc.output[:200]}")
            logger.warning("Failed to update %s: %s", pkg, exc.output[:200])

    # Re-download FinBERT model (HuggingFace checks revision, no-ops if current)
    try:
        os.environ["HF_HOME"] = hf_cache_dir
        if packages_dir not in sys.path:
            sys.path.insert(0, packages_dir)
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        AutoTokenizer.from_pretrained("ProsusAI/finbert")
        AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        logger.info("FinBERT model cache verified/updated")
    except Exception as exc:
        results["errors"].append(f"finbert: {exc}")
        logger.warning("Failed to update FinBERT model: %s", exc)

    return results
