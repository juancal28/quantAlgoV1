"""quant dashboard — live auto-refresh composite view."""

from __future__ import annotations

import time

import typer
from rich.console import Console
from rich.live import Live

from cli import client
from cli.views.dashboard_view import build_dashboard


def _fetch_all() -> dict:
    status_data = client.get("/status")
    news = client.get("/news/recent", params={"minutes": 120, "limit": 5})
    strategies = client.get("/strategies")
    runs = client.get("/runs/recent", params={"limit": 5})

    # Fetch PnL for active strategies
    pnl_data: dict = {}
    active = [s for s in strategies if s.get("status") == "active"]
    for s in active[:3]:  # limit to 3 to keep refresh fast
        name = s.get("name", "")
        if name:
            pnl_data[name] = client.get("/pnl/daily", params={"strategy": name, "days": 7})

    return {
        "status": status_data,
        "news": news,
        "strategies": strategies,
        "runs": runs,
        "pnl": pnl_data,
    }


def dashboard(
    interval: int = typer.Option(15, "-i", "--interval", help="Refresh interval in seconds"),
) -> None:
    """Live auto-refreshing dashboard. Ctrl+C to exit."""
    console = Console()
    console.print(f"[bold]Dashboard[/] — refreshing every {interval}s (Ctrl+C to exit)\n")

    try:
        with Live(console=console, refresh_per_second=1) as live:
            while True:
                data = _fetch_all()
                panel = build_dashboard(
                    status_data=data["status"],
                    news=data["news"],
                    strategies=data["strategies"],
                    runs=data["runs"],
                    pnl_data=data["pnl"],
                )
                live.update(panel)
                time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Dashboard stopped.[/]")
