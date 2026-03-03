"""Rich view for news articles."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from rich.console import Console
from rich.table import Table


def _format_published(raw: str) -> str:
    """Format ISO timestamp into a readable 'Mar 02  14:30' style string."""
    if not raw:
        return "--"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%b %d  %H:%M")
    except (ValueError, TypeError):
        return raw[:16]


def _sentiment_style(label: str | None, score: float | None) -> tuple[str, str]:
    if label is None:
        return "[dim]--[/]", "[dim]--[/]"
    if label == "positive":
        return f"[green]{score:+.2f}[/]", f"[green]{label}[/]"
    if label == "negative":
        return f"[red]{score:+.2f}[/]", f"[red]{label}[/]"
    return f"[dim]{score:+.2f}[/]", f"[dim]{label}[/]"


def render_news(articles: list[dict[str, Any]], console: Console | None = None) -> None:
    console = console or Console()

    if not articles:
        console.print("[dim]No recent news articles.[/]")
        return

    table = Table(title="Recent News", show_lines=False)
    table.add_column("Published", style="dim", width=14)
    table.add_column("Title", max_width=50)
    table.add_column("Source", width=12)
    table.add_column("Score", justify="right", width=7)
    table.add_column("Sentiment", width=10)
    table.add_column("Tickers", width=20)

    for a in articles:
        score_text, label_text = _sentiment_style(
            a.get("sentiment_label"), a.get("sentiment_score")
        )
        tickers = ", ".join(a.get("tickers", []))
        table.add_row(
            _format_published(a.get("published_at", "")),
            a.get("title", "")[:50],
            a.get("source", ""),
            score_text,
            label_text,
            tickers or "[dim]--[/]",
        )

    console.print(table)
