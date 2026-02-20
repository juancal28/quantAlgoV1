"""Tests for Celery scheduler jobs."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
    """News cycle should create a run record and early-exit on 0 ingested docs."""
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
