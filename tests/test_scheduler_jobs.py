"""Tests for Celery scheduler jobs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.storage.repos import run_repo


@pytest.mark.asyncio
async def test_paper_trade_tick_no_active_strategies(db_session: AsyncSession):
    """When no active strategies exist, tick does nothing."""
    from apps.scheduler.jobs import _run_paper_trade_tick_all_async

    result = await _run_paper_trade_tick_all_async(_session=db_session)
    assert result["ticked"] == []


@pytest.mark.asyncio
async def test_news_cycle_creates_run_record(db_session: AsyncSession):
    """News cycle should create a run record and exit early on 0 ingested docs."""
    from apps.scheduler.jobs import _run_news_cycle_async

    mock_ingest_output = AsyncMock(ingested=0, doc_ids=[])
    mock_ingest = AsyncMock(return_value=mock_ingest_output)

    with patch(
        "apps.mcp_server.tools.ingest.ingest_latest_news", mock_ingest
    ):
        result = await _run_news_cycle_async(_session=db_session)

    assert result["early_exit"] == "no_new_docs"
    assert result["ingested"] == 0


@pytest.mark.asyncio
async def test_news_cycle_with_existing_run(db_session: AsyncSession):
    """News cycle with a pre-created run_id should use that run record."""
    from apps.scheduler.jobs import _run_news_cycle_async

    # Create a run record first
    run = await run_repo.create_run(db_session, run_type="ingest")
    await db_session.flush()
    run_id_str = str(run.id)

    mock_ingest_output = AsyncMock(ingested=0, doc_ids=[])
    mock_ingest = AsyncMock(return_value=mock_ingest_output)

    with patch(
        "apps.mcp_server.tools.ingest.ingest_latest_news", mock_ingest
    ):
        result = await _run_news_cycle_async(
            run_id=run_id_str, _session=db_session
        )

    assert result["early_exit"] == "no_new_docs"


# ---------------------------------------------------------------------------
# Singleton lock tests
# ---------------------------------------------------------------------------


def test_news_cycle_skips_when_lock_held():
    """run_news_cycle returns skipped=True when Redis lock is already held."""
    from apps.scheduler.jobs import run_news_cycle

    with patch("apps.scheduler.jobs._is_scheduler_paused", return_value=False), \
         patch("apps.scheduler.jobs._acquire_singleton_lock", return_value=False):
        result = run_news_cycle(run_id=None, agent_name=None)

    assert result["skipped"] is True
    assert result["reason"] == "lock_held"


def test_news_cycle_acquires_and_releases_lock():
    """run_news_cycle acquires lock, runs, then releases lock."""
    from apps.scheduler.jobs import run_news_cycle

    mock_acquire = MagicMock(return_value=True)
    mock_release = MagicMock()

    with (
        patch("apps.scheduler.jobs._is_scheduler_paused", return_value=False),
        patch("apps.scheduler.jobs._acquire_singleton_lock", mock_acquire),
        patch("apps.scheduler.jobs._release_singleton_lock", mock_release),
        patch(
            "apps.scheduler.jobs.asyncio.run",
            return_value={"ingested": 0, "early_exit": "no_new_docs"},
        ),
    ):
        result = run_news_cycle(run_id=None, agent_name=None)

    mock_acquire.assert_called_once()
    mock_release.assert_called_once()
    assert result["ingested"] == 0


def test_news_cycle_releases_lock_on_error():
    """Lock is released even when the news cycle raises an exception."""
    from apps.scheduler.jobs import run_news_cycle

    mock_acquire = MagicMock(return_value=True)
    mock_release = MagicMock()

    with (
        patch("apps.scheduler.jobs._is_scheduler_paused", return_value=False),
        patch("apps.scheduler.jobs._acquire_singleton_lock", mock_acquire),
        patch("apps.scheduler.jobs._release_singleton_lock", mock_release),
        patch(
            "apps.scheduler.jobs.asyncio.run",
            side_effect=RuntimeError("boom"),
        ),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            run_news_cycle(run_id=None, agent_name=None)

    mock_release.assert_called_once()


def test_paper_trade_tick_skips_when_lock_held():
    """run_paper_trade_tick_all returns skipped=True when lock is held."""
    from apps.scheduler.jobs import run_paper_trade_tick_all

    with patch("apps.scheduler.jobs._is_scheduler_paused", return_value=False), \
         patch("apps.scheduler.jobs._acquire_singleton_lock", return_value=False):
        result = run_paper_trade_tick_all()

    assert result["skipped"] is True
    assert result["reason"] == "lock_held"


def test_news_cycle_lock_name_includes_agent():
    """Lock name is agent-specific for multi-agent setups."""
    from apps.scheduler.jobs import run_news_cycle

    mock_acquire = MagicMock(return_value=False)

    with patch("apps.scheduler.jobs._is_scheduler_paused", return_value=False), \
         patch("apps.scheduler.jobs._acquire_singleton_lock", mock_acquire):
        run_news_cycle(run_id=None, agent_name="tech")

    mock_acquire.assert_called_once()
    lock_name = mock_acquire.call_args[0][0]
    assert lock_name == "news_cycle:tech"
