"""News endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db
from core.storage.repos import news_repo

router = APIRouter(prefix="/news", tags=["news"])


class NewsArticleResponse(BaseModel):
    id: str
    title: str
    source: str
    source_url: str
    published_at: datetime
    sentiment_score: float | None = None
    sentiment_label: str | None = None
    tickers: list[str]


@router.get("/recent", response_model=list[NewsArticleResponse])
async def get_recent_news(
    minutes: int = Query(default=120, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    by_published: bool = Query(default=True),
    session: AsyncSession = Depends(get_db),
) -> list[NewsArticleResponse]:
    docs = await news_repo.get_recent(session, minutes=minutes, limit=limit, by_published=by_published)
    return [
        NewsArticleResponse(
            id=str(d.id),
            title=d.title,
            source=d.source,
            source_url=d.source_url,
            published_at=d.published_at,
            sentiment_score=d.sentiment_score,
            sentiment_label=d.sentiment_label,
            tickers=(d.metadata_ or {}).get("tickers", []),
        )
        for d in docs
    ]
