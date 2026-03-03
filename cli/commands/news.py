"""quant news — recent news with sentiment."""

from __future__ import annotations

import typer

from cli import client
from cli.views.news_view import render_news


def news(
    minutes: int = typer.Option(120, "-m", "--minutes", help="Lookback window in minutes"),
    limit: int = typer.Option(20, "-n", "--limit", help="Max articles to show"),
) -> None:
    """Show recent news articles with sentiment scores."""
    articles = client.get("/news/recent", params={"minutes": minutes, "limit": limit})
    render_news(articles)
