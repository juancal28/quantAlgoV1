"""ML dependency management endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ml-deps", tags=["ml-deps"])


class MlDepsUpdateResponse(BaseModel):
    status: str
    task_id: str | None = None


@router.post("/update", response_model=MlDepsUpdateResponse)
async def trigger_ml_deps_update() -> MlDepsUpdateResponse:
    """Trigger an ML dependency update (torch, transformers, FinBERT) on the persistent volume."""
    try:
        from apps.scheduler.jobs import run_ml_deps_update

        result = run_ml_deps_update.delay()
        return MlDepsUpdateResponse(status="dispatched", task_id=result.id)
    except Exception:
        logger.warning("Celery unavailable, ml_deps_update not dispatched", exc_info=True)
        return MlDepsUpdateResponse(status="failed")
