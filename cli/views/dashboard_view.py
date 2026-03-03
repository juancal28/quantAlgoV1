"""Composite dashboard layout for rich.live auto-refresh."""

from __future__ import annotations

from typing import Any

from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table

from cli.views.news_view import _sentiment_style
from cli.views.pnl_view import _pnl_style, _sparkline
from cli.views.runs_view import _format_timestamp, _status_style as _run_status
from cli.views.strategies_view import _status_style as _strat_status


def _last_news_cycle(runs: list[dict[str, Any]]) -> str:
    """Find the most recent completed news cycle (ingest) run and format its timestamp."""
    for r in runs:
        if r.get("run_type") == "ingest" and r.get("status") in ("ok", "fail"):
            ts = _format_timestamp(r.get("ended_at") or r.get("started_at"))
            status = r.get("status", "")
            if status == "ok":
                return f"[green]{ts}[/]"
            return f"[red]{ts} (failed)[/]"
    return "[dim]never[/]"


def _status_panel(data: dict[str, Any], runs: list[dict[str, Any]]) -> Panel:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("K", style="bold")
    table.add_column("V")
    mode = data.get("trading_mode", "?")
    table.add_row("Mode", f"[green]{mode}[/]" if mode == "paper" else f"[red]{mode}[/]")
    market = data.get("market_open", False)
    table.add_row("Market", "[green]OPEN[/]" if market else "[dim]CLOSED[/]")
    table.add_row("News (2h)", str(data.get("news_count_last_2h", 0)))
    table.add_row("Last Ingest", _last_news_cycle(runs))
    counts = data.get("strategy_counts", {})
    table.add_row("Strategies", ", ".join(f"{k}:{v}" for k, v in counts.items()) or "--")
    services = data.get("services", {})
    for svc, st in services.items():
        c = "green" if st == "ok" else "red"
        table.add_row(svc, f"[{c}]{st}[/]")
    return Panel(table, title="Status", border_style="blue")


def _news_panel(articles: list[dict[str, Any]]) -> Panel:
    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("Title", max_width=35)
    table.add_column("Score", justify="right", width=7)
    table.add_column("Tickers", width=14)
    for a in articles[:5]:
        score_text, _ = _sentiment_style(a.get("sentiment_label"), a.get("sentiment_score"))
        table.add_row(
            (a.get("title") or "")[:35],
            score_text,
            ", ".join(a.get("tickers", []))[:14] or "--",
        )
    return Panel(table, title="Recent News", border_style="green")


def _strategies_panel(strategies: list[dict[str, Any]]) -> Panel:
    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("Name", width=20)
    table.add_column("V", width=3)
    table.add_column("Status", width=16)
    for s in strategies[:8]:
        table.add_row(
            s.get("name", "")[:20],
            str(s.get("version", "")),
            _strat_status(s.get("status", "")),
        )
    return Panel(table, title="Strategies", border_style="cyan")


def _runs_panel(runs: list[dict[str, Any]]) -> Panel:
    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("Type", width=12)
    table.add_column("Status", width=8)
    table.add_column("Started", width=20)
    for r in runs[:5]:
        table.add_row(
            r.get("run_type", ""),
            _run_status(r.get("status", "")),
            _format_timestamp(r.get("started_at")),
        )
    return Panel(table, title="Recent Runs", border_style="yellow")


def _pnl_panel(pnl_data: dict[str, list[dict[str, Any]]]) -> Panel:
    lines: list[str] = []
    for name, snapshots in pnl_data.items():
        if not snapshots:
            continue
        latest = snapshots[0]
        realized = [s.get("realized_pnl", 0) for s in snapshots]
        spark = _sparkline(realized)
        lines.append(
            f"  {name}: realized={_pnl_style(latest.get('realized_pnl', 0))}  "
            f"unrealized={_pnl_style(latest.get('unrealized_pnl', 0))}  {spark}"
        )
    content = "\n".join(lines) if lines else "[dim]No PnL data.[/]"
    return Panel(content, title="PnL Summary", border_style="magenta")


def build_dashboard(
    status_data: dict[str, Any],
    news: list[dict[str, Any]],
    strategies: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    pnl_data: dict[str, list[dict[str, Any]]],
) -> Group:
    top = Columns([_status_panel(status_data, runs), _news_panel(news)], equal=True, expand=True)
    mid = Columns([_strategies_panel(strategies), _runs_panel(runs)], equal=True, expand=True)
    bottom = _pnl_panel(pnl_data)
    return Group(top, mid, bottom)
