"""Tests for scheduler pause/resume functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestSchedulerPauseFlag:
    """Test that _is_scheduler_paused checks Redis correctly."""

    def test_paused_when_key_exists(self):
        from apps.scheduler.jobs import _is_scheduler_paused

        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1

        with patch("apps.scheduler.jobs._get_redis_client", return_value=mock_redis):
            assert _is_scheduler_paused() is True
            mock_redis.exists.assert_called_once_with("scheduler:paused")

    def test_not_paused_when_key_missing(self):
        from apps.scheduler.jobs import _is_scheduler_paused

        mock_redis = MagicMock()
        mock_redis.exists.return_value = 0

        with patch("apps.scheduler.jobs._get_redis_client", return_value=mock_redis):
            assert _is_scheduler_paused() is False


class TestTasksSkipWhenPaused:
    """Test that all scheduled tasks skip when paused."""

    @pytest.fixture(autouse=True)
    def _pause_scheduler(self):
        with patch(
            "apps.scheduler.jobs._is_scheduler_paused", return_value=True
        ):
            yield

    def test_news_cycle_skips(self):
        from apps.scheduler.jobs import run_news_cycle

        result = run_news_cycle(MagicMock())
        assert result == {"skipped": True, "reason": "scheduler_paused"}

    def test_paper_trade_tick_skips(self):
        from apps.scheduler.jobs import run_paper_trade_tick_all

        result = run_paper_trade_tick_all()
        assert result == {"skipped": True, "reason": "scheduler_paused"}

    def test_auto_approve_skips(self):
        from apps.scheduler.jobs import run_auto_approve

        result = run_auto_approve()
        assert result == {"skipped": True, "reason": "scheduler_paused"}

    def test_expire_strategies_skips(self):
        from apps.scheduler.jobs import run_expire_strategies

        result = run_expire_strategies()
        assert result == {"skipped": True, "reason": "scheduler_paused"}

    def test_news_cleanup_skips(self):
        from apps.scheduler.jobs import run_news_cleanup

        result = run_news_cleanup()
        assert result == {"skipped": True, "reason": "scheduler_paused"}


class TestTasksRunWhenNotPaused:
    """Verify tasks don't skip when scheduler is not paused."""

    def test_news_cycle_does_not_skip(self):
        """When not paused, news_cycle proceeds (hits the lock, not the pause guard)."""
        from apps.scheduler.jobs import run_news_cycle

        with patch("apps.scheduler.jobs._is_scheduler_paused", return_value=False), \
             patch("apps.scheduler.jobs._acquire_singleton_lock", return_value=False):
            result = run_news_cycle(MagicMock())
            # Lock not acquired = skipped for lock reason, NOT pause
            assert result == {"skipped": True, "reason": "lock_held"}


class TestSchedulerAPIEndpoints:
    """Test the FastAPI scheduler router."""

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient

        from apps.api.routers.scheduler import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_pause(self, client):
        mock_redis = MagicMock()
        with patch("apps.api.routers.scheduler._redis", return_value=mock_redis):
            resp = client.post("/scheduler/pause")
            assert resp.status_code == 200
            assert resp.json() == {"paused": True}
            mock_redis.set.assert_called_once_with("scheduler:paused", "1")

    def test_resume(self, client):
        mock_redis = MagicMock()
        with patch("apps.api.routers.scheduler._redis", return_value=mock_redis):
            resp = client.post("/scheduler/resume")
            assert resp.status_code == 200
            assert resp.json() == {"paused": False}
            mock_redis.delete.assert_called_once_with("scheduler:paused")

    def test_status_paused(self, client):
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1
        with patch("apps.api.routers.scheduler._redis", return_value=mock_redis):
            resp = client.get("/scheduler/status")
            assert resp.status_code == 200
            assert resp.json() == {"paused": True}

    def test_status_running(self, client):
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 0
        with patch("apps.api.routers.scheduler._redis", return_value=mock_redis):
            resp = client.get("/scheduler/status")
            assert resp.status_code == 200
            assert resp.json() == {"paused": False}
