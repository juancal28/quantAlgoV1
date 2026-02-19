"""FastAPI application entry point."""

from __future__ import annotations

from core.config import get_settings

# Enforce TRADING_MODE=paper guard at import time
get_settings()

from fastapi import FastAPI

from apps.api.routers.health import router as health_router
from apps.api.routers.strategies import router as strategies_router

app = FastAPI(title="Quant News-RAG Trading System", version="0.1.0")
app.include_router(health_router)
app.include_router(strategies_router)
