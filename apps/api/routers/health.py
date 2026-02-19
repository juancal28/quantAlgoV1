"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    settings = get_settings()
    return {"status": "ok", "trading_mode": settings.TRADING_MODE}
