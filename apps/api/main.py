"""FastAPI application entry point."""

from __future__ import annotations

from core.config import get_settings

# Enforce TRADING_MODE=paper guard at import time
get_settings()

from fastapi import FastAPI

from apps.api.routers.autonomous import router as autonomous_router
from apps.api.routers.backtests import router as backtests_router
from apps.api.routers.health import router as health_router
from apps.api.routers.ml_deps import router as ml_deps_router
from apps.api.routers.news import router as news_router
from apps.api.routers.pnl import router as pnl_router
from apps.api.routers.runs import router as runs_router
from apps.api.routers.scheduler import router as scheduler_router
from apps.api.routers.status import router as status_router
from apps.api.routers.strategies import router as strategies_router

app = FastAPI(title="Quant News-RAG Trading System", version="0.1.0")
app.include_router(health_router)
app.include_router(status_router)
app.include_router(strategies_router)
app.include_router(backtests_router)
app.include_router(news_router)
app.include_router(runs_router)
app.include_router(pnl_router)
app.include_router(scheduler_router)
app.include_router(ml_deps_router)
app.include_router(autonomous_router)
