"""Celery worker configuration."""

from __future__ import annotations

from celery import Celery

from core.config import get_settings


def create_celery_app() -> Celery:
    """Create and configure the Celery application."""
    settings = get_settings()

    app = Celery("quant_scheduler")
    app.conf.update(
        broker_url=settings.REDIS_URL,
        result_backend=settings.REDIS_URL,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        include=["apps.scheduler.jobs"],
        beat_schedule={
            "news-cycle-periodic": {
                "task": "apps.scheduler.jobs.run_news_cycle",
                "schedule": settings.NEWS_POLL_INTERVAL_SECONDS,
            },
            "paper-trade-tick-periodic": {
                "task": "apps.scheduler.jobs.run_paper_trade_tick_all",
                "schedule": 60.0,
            },
        },
    )

    return app


celery_app = create_celery_app()
