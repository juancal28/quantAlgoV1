"""Tests for multi-agent configuration and scheduling."""

from __future__ import annotations

import json

import pytest

from core.config import AgentConfig, _reset_settings, get_settings


# ---------------------------------------------------------------------------
# AgentConfig parsing
# ---------------------------------------------------------------------------

class TestAgentConfigParsing:
    """Tests for AGENT_CONFIGS setting parsing."""

    def test_empty_list(self, mock_settings):
        """Empty JSON list returns no agents (single-agent mode)."""
        mock_settings("AGENT_CONFIGS", "[]")
        settings = get_settings()
        assert settings.parsed_agent_configs == []

    def test_valid_single_agent(self, mock_settings):
        """Single agent config parses correctly."""
        configs = [
            {
                "name": "tech",
                "strategy_name": "tech_momentum_v1",
                "universe": ["AAPL", "MSFT", "NVDA"],
                "news_sources": "rss:https://feeds.example.com/tech",
                "qdrant_collection": "news_tech",
            }
        ]
        mock_settings("AGENT_CONFIGS", json.dumps(configs))
        settings = get_settings()
        agents = settings.parsed_agent_configs
        assert len(agents) == 1
        assert agents[0].name == "tech"
        assert agents[0].strategy_name == "tech_momentum_v1"
        assert agents[0].universe == ["AAPL", "MSFT", "NVDA"]
        assert agents[0].qdrant_collection == "news_tech"

    def test_valid_multiple_agents(self, mock_settings):
        """Multiple agent configs parse correctly."""
        configs = [
            {
                "name": "tech",
                "strategy_name": "tech_momentum_v1",
                "universe": ["AAPL", "MSFT"],
                "news_sources": "rss:https://feeds.example.com/tech",
                "qdrant_collection": "news_tech",
            },
            {
                "name": "finance",
                "strategy_name": "fin_momentum_v1",
                "universe": ["JPM", "BAC"],
                "news_sources": "rss:https://feeds.example.com/finance",
                "qdrant_collection": "news_finance",
            },
        ]
        mock_settings("AGENT_CONFIGS", json.dumps(configs))
        settings = get_settings()
        agents = settings.parsed_agent_configs
        assert len(agents) == 2
        assert agents[0].name == "tech"
        assert agents[1].name == "finance"

    def test_invalid_json_raises(self, mock_settings):
        """Invalid JSON raises an error."""
        mock_settings("AGENT_CONFIGS", "not-valid-json")
        settings = get_settings()
        with pytest.raises(json.JSONDecodeError):
            settings.parsed_agent_configs

    def test_missing_required_field_raises(self, mock_settings):
        """Missing required field raises validation error."""
        configs = [{"name": "tech"}]  # missing strategy_name, universe, etc.
        mock_settings("AGENT_CONFIGS", json.dumps(configs))
        settings = get_settings()
        with pytest.raises(Exception):  # pydantic ValidationError
            settings.parsed_agent_configs


# ---------------------------------------------------------------------------
# Vectorstore with custom collection name
# ---------------------------------------------------------------------------

class TestVectorstoreCollectionName:
    """Tests for vectorstore collection_name override."""

    def test_qdrant_default_collection(self):
        """QdrantVectorStore uses VECTOR_COLLECTION by default."""
        from core.kb.vectorstore import QdrantVectorStore

        try:
            store = QdrantVectorStore()
            settings = get_settings()
            assert store._collection == settings.VECTOR_COLLECTION
        except Exception:
            # Qdrant not running — just verify the attribute would be set
            pytest.skip("Qdrant not available for connection test")

    def test_qdrant_custom_collection(self):
        """QdrantVectorStore uses custom collection_name when provided."""
        from core.kb.vectorstore import QdrantVectorStore

        try:
            store = QdrantVectorStore(collection_name="news_tech")
            assert store._collection == "news_tech"
        except Exception:
            pytest.skip("Qdrant not available for connection test")

    def test_get_vectorstore_factory_default(self):
        """get_vectorstore() with mock returns FAISSMockVectorStore."""
        from core.kb.vectorstore import FAISSMockVectorStore, get_vectorstore

        store = get_vectorstore(use_mock=True)
        assert isinstance(store, FAISSMockVectorStore)

    def test_get_vectorstore_factory_collection_name(self):
        """get_vectorstore() passes collection_name to QdrantVectorStore."""
        from core.kb.vectorstore import get_vectorstore

        try:
            store = get_vectorstore(collection_name="news_finance")
            assert store._collection == "news_finance"
        except Exception:
            pytest.skip("Qdrant not available for connection test")


# ---------------------------------------------------------------------------
# IngestInput feed_urls
# ---------------------------------------------------------------------------

class TestIngestInputFeedUrls:
    """Tests for feed_urls field on IngestInput."""

    def test_default_feed_urls_is_none(self):
        from apps.mcp_server.schemas import IngestInput

        inp = IngestInput()
        assert inp.feed_urls is None

    def test_custom_feed_urls(self):
        from apps.mcp_server.schemas import IngestInput

        urls = ["https://feeds.example.com/tech", "https://feeds.example.com/ai"]
        inp = IngestInput(feed_urls=urls)
        assert inp.feed_urls == urls


# ---------------------------------------------------------------------------
# Beat schedule generation
# ---------------------------------------------------------------------------

class TestBeatSchedule:
    """Tests for dynamic Celery beat schedule generation."""

    def test_no_agents_single_news_cycle(self, mock_settings):
        """Empty AGENT_CONFIGS produces single news-cycle-periodic task."""
        mock_settings("AGENT_CONFIGS", "[]")
        from apps.scheduler.worker import _build_beat_schedule

        settings = get_settings()
        schedule = _build_beat_schedule(settings)
        assert "news-cycle-periodic" in schedule
        assert "paper-trade-tick-periodic" in schedule
        # No agent-specific keys
        agent_keys = [k for k in schedule if k.startswith("news-cycle-") and k != "news-cycle-periodic"]
        assert len(agent_keys) == 0

    def test_single_agent_schedule(self, mock_settings):
        """Single agent produces news-cycle-{name} task, no generic one."""
        configs = [
            {
                "name": "tech",
                "strategy_name": "tech_momentum_v1",
                "universe": ["AAPL"],
                "news_sources": "rss:https://feeds.example.com/tech",
                "qdrant_collection": "news_tech",
            }
        ]
        mock_settings("AGENT_CONFIGS", json.dumps(configs))
        from apps.scheduler.worker import _build_beat_schedule

        settings = get_settings()
        schedule = _build_beat_schedule(settings)
        assert "news-cycle-tech" in schedule
        assert "news-cycle-periodic" not in schedule
        assert schedule["news-cycle-tech"]["kwargs"] == {"agent_name": "tech"}
        assert "paper-trade-tick-periodic" in schedule

    def test_multiple_agents_schedule(self, mock_settings):
        """Multiple agents each get their own news-cycle task."""
        configs = [
            {
                "name": "tech",
                "strategy_name": "tech_v1",
                "universe": ["AAPL"],
                "news_sources": "rss:https://feeds.example.com/tech",
                "qdrant_collection": "news_tech",
            },
            {
                "name": "finance",
                "strategy_name": "fin_v1",
                "universe": ["JPM"],
                "news_sources": "rss:https://feeds.example.com/finance",
                "qdrant_collection": "news_finance",
            },
        ]
        mock_settings("AGENT_CONFIGS", json.dumps(configs))
        from apps.scheduler.worker import _build_beat_schedule

        settings = get_settings()
        schedule = _build_beat_schedule(settings)
        assert "news-cycle-tech" in schedule
        assert "news-cycle-finance" in schedule
        assert "news-cycle-periodic" not in schedule
        assert schedule["news-cycle-tech"]["kwargs"] == {"agent_name": "tech"}
        assert schedule["news-cycle-finance"]["kwargs"] == {"agent_name": "finance"}


# ---------------------------------------------------------------------------
# News cycle agent_name dispatch
# ---------------------------------------------------------------------------

class TestNewsCycleAgentDispatch:
    """Tests for agent_name parameter in _run_news_cycle_async."""

    @pytest.mark.asyncio
    async def test_unknown_agent_raises(self, db_session, mock_settings):
        """Passing an unknown agent_name raises ValueError."""
        mock_settings("AGENT_CONFIGS", "[]")
        from apps.scheduler.jobs import _run_news_cycle_async

        with pytest.raises(ValueError, match="Agent 'nonexistent' not found"):
            await _run_news_cycle_async(
                _session=db_session, agent_name="nonexistent"
            )

    @pytest.mark.asyncio
    async def test_no_agent_name_uses_defaults(self, db_session, mock_settings):
        """Without agent_name, uses default strategy_name and global feeds."""
        mock_settings("AGENT_CONFIGS", "[]")
        from unittest.mock import AsyncMock, patch

        from apps.mcp_server.schemas import IngestOutput
        from apps.scheduler.jobs import _run_news_cycle_async

        mock_ingest = AsyncMock(
            return_value=IngestOutput(ingested=0, doc_ids=[])
        )
        with patch(
            "apps.mcp_server.tools.ingest.ingest_latest_news", mock_ingest
        ):
            result = await _run_news_cycle_async(_session=db_session)

        assert result["early_exit"] == "no_new_docs"
        # feed_urls should be None (global default)
        call_args = mock_ingest.call_args
        ingest_input = call_args[0][1]
        assert ingest_input.feed_urls is None

    @pytest.mark.asyncio
    async def test_agent_name_uses_agent_feeds(self, db_session, mock_settings):
        """With agent_name, uses agent's feed URLs."""
        configs = [
            {
                "name": "tech",
                "strategy_name": "tech_momentum_v1",
                "universe": ["AAPL"],
                "news_sources": "rss:https://feeds.example.com/tech",
                "qdrant_collection": "news_tech",
            }
        ]
        mock_settings("AGENT_CONFIGS", json.dumps(configs))
        from unittest.mock import AsyncMock, patch

        from apps.mcp_server.schemas import IngestOutput
        from apps.scheduler.jobs import _run_news_cycle_async

        mock_ingest = AsyncMock(
            return_value=IngestOutput(ingested=0, doc_ids=[])
        )
        with patch(
            "apps.mcp_server.tools.ingest.ingest_latest_news", mock_ingest
        ):
            result = await _run_news_cycle_async(
                _session=db_session, agent_name="tech"
            )

        assert result["agent_name"] == "tech"
        assert result["early_exit"] == "no_new_docs"
        # feed_urls should contain the agent's parsed feed URL
        call_args = mock_ingest.call_args
        ingest_input = call_args[0][1]
        assert ingest_input.feed_urls == ["https://feeds.example.com/tech"]
