"""Celery worker configuration."""

from __future__ import annotations

from celery import Celery

from core.config import get_settings


def _build_beat_schedule(settings) -> dict:
    """Build the Celery beat schedule, dynamically adding per-agent tasks."""
    schedule: dict = {}

    agent_configs = settings.parsed_agent_configs
    if agent_configs:
        # Multi-agent mode: one news-cycle task per agent
        for agent_cfg in agent_configs:
            schedule[f"news-cycle-{agent_cfg.name}"] = {
                "task": "apps.scheduler.jobs.run_news_cycle",
                "schedule": settings.NEWS_POLL_INTERVAL_SECONDS,
                "kwargs": {"agent_name": agent_cfg.name},
            }
    else:
        # Single-agent mode (backward compatible)
        schedule["news-cycle-periodic"] = {
            "task": "apps.scheduler.jobs.run_news_cycle",
            "schedule": settings.NEWS_POLL_INTERVAL_SECONDS,
        }

    # paper-trade-tick always runs (iterates all active strategies)
    schedule["paper-trade-tick-periodic"] = {
        "task": "apps.scheduler.jobs.run_paper_trade_tick_all",
        "schedule": 60.0,
    }

    # Auto-approve pending strategies (only when configured)
    if settings.PENDING_APPROVAL_AUTO_APPROVE_MINUTES > 0:
        schedule["auto-approve-periodic"] = {
            "task": "apps.scheduler.jobs.run_auto_approve",
            "schedule": 60.0,
        }

    return schedule


def create_celery_app() -> Celery:
    """Create and configure the Celery application."""
    settings = get_settings()

    app = Celery("quant_scheduler")
    app.conf.update(
        broker_url=settings.REDIS_URL,
        result_backend=settings.REDIS_URL,
        result_expires=3600,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        broker_transport_options={"visibility_timeout": 600},
        include=["apps.scheduler.jobs"],
        beat_schedule=_build_beat_schedule(settings),
    )

    return app


celery_app = create_celery_app()
