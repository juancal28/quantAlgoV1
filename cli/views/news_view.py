"""Rich view for news articles."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from rich.console import Console
from rich.table import Table


_PACIFIC = ZoneInfo("America/Los_Angeles")


def _format_published(raw: str) -> str:
    """Format ISO timestamp into a readable 'Mar 02  14:30 PST' style string."""
    if not raw:
        return "--"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        dt_pac = dt.astimezone(_PACIFIC)
        tz_abbr = dt_pac.strftime("%Z")  # PST or PDT
        return dt_pac.strftime(f"%b %d  %H:%M {tz_abbr}")
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


def _friendly_source(raw: str) -> str:
    """Extract a short, human-readable source name from a URL or prefixed string."""
    # Strip scheme prefixes like "rss:"
    url = raw.split(":", 1)[1] if ":" in raw else raw
    url = url.lstrip("/")
    # Extract domain
    try:
        from urllib.parse import urlparse
        hostname = urlparse(f"https://{url}" if "//" not in url else url).hostname or url
    except Exception:
        hostname = url
    # Remove common prefixes
    if hostname.startswith("www."):
        hostname = hostname[4:]
    # Remove common suffixes for brevity
    if hostname.startswith("feeds."):
        hostname = hostname[6:]
    # Return just the domain name part (e.g. "finance.yahoo.com" -> "Yahoo Finance")
    _KNOWN = {
        "finance.yahoo.com": "Yahoo Finance",
        "yahoo.com": "Yahoo Finance",
        "reuters.com": "Reuters",
        "bloomberg.com": "Bloomberg",
        "cnbc.com": "CNBC",
        "wsj.com": "WSJ",
        "marketwatch.com": "MarketWatch",
        "investing.com": "Investing.com",
        "seekingalpha.com": "Seeking Alpha",
        "ft.com": "Financial Times",
        "barrons.com": "Barron's",
        "benzinga.com": "Benzinga",
        "fool.com": "Motley Fool",
    }
    for domain, name in _KNOWN.items():
        if domain in hostname:
            return name
    # Fallback: capitalize first segment of domain
    return hostname.split(".")[0].capitalize()


def render_news(articles: list[dict[str, Any]], console: Console | None = None) -> None:
    console = console or Console()

    if not articles:
        console.print("[dim]No recent news articles.[/]")
        return

    table = Table(title="Recent News", show_lines=False)
    table.add_column("Published", style="dim", width=18)
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
            _friendly_source(a.get("source", "")),
            score_text,
            label_text,
            tickers or "[dim]--[/]",
        )

    console.print(table)
