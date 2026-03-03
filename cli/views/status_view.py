"""Rich view for system status."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def render_status(data: dict[str, Any], console: Console | None = None) -> None:
    console = console or Console()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")

    # Trading mode
    mode = data.get("trading_mode", "unknown")
    mode_style = "green" if mode == "paper" else "red bold"
    table.add_row("Trading Mode", f"[{mode_style}]{mode}[/]")

    # Paper guard
    guard = data.get("paper_guard", False)
    guard_style = "green" if guard else "red bold"
    table.add_row("Paper Guard", f"[{guard_style}]{guard}[/]")

    # Market
    market = data.get("market_open", False)
    market_text = "[green]OPEN[/]" if market else "[dim]CLOSED[/]"
    table.add_row("Market", market_text)

    # Last ingest
    last = data.get("last_ingest_run")
    if last:
        table.add_row("Last Ingest", f"{last.get('started_at', '?')}  [{last.get('status', '?')}]")
    else:
        table.add_row("Last Ingest", "[dim]none[/]")

    # News count
    table.add_row("News (2h)", str(data.get("news_count_last_2h", 0)))

    # Strategy counts
    counts = data.get("strategy_counts", {})
    parts = [f"{status}: {n}" for status, n in counts.items()]
    table.add_row("Strategies", ", ".join(parts) if parts else "[dim]none[/]")

    # Services
    services = data.get("services", {})
    svc_parts = []
    for svc, state in services.items():
        style = "green" if state == "ok" else "red"
        svc_parts.append(f"[{style}]{svc}={state}[/]")
    table.add_row("Services", "  ".join(svc_parts) if svc_parts else "[dim]none[/]")

    console.print(Panel(table, title="System Status", border_style="blue"))
