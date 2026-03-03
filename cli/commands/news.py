"""quant news — recent news with sentiment."""

from __future__ import annotations

import typer

from cli import client
from cli.views.news_view import render_news


def news(
    minutes: int = typer.Option(120, "-m", "--minutes", help="Lookback window in minutes"),
    limit: int = typer.Option(20, "-n", "--limit", help="Max articles to show"),
    ingested: bool = typer.Option(False, "--ingested", help="Sort by ingestion time instead of published date"),
) -> None:
    """Show recent news articles with sentiment scores."""
    params: dict = {"minutes": minutes, "limit": limit}
    if ingested:
        params["by_published"] = False
    articles = client.get("/news/recent", params=params)
    render_news(articles)
