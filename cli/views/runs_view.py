"""Rich view for pipeline runs."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table


def _status_style(status: str) -> str:
    if status == "ok":
        return f"[green]{status}[/]"
    if status == "fail":
        return f"[red]{status}[/]"
    if status == "running":
        return f"[yellow]{status}[/]"
    return status


def render_runs(runs: list[dict[str, Any]], console: Console | None = None) -> None:
    console = console or Console()

    if not runs:
        console.print("[dim]No recent runs.[/]")
        return

    table = Table(title="Recent Runs")
    table.add_column("Type", width=16)
    table.add_column("Status", width=10)
    table.add_column("Started", style="dim", width=20)
    table.add_column("Ended", style="dim", width=20)
    table.add_column("Details", max_width=40)

    for r in runs:
        details = r.get("details") or {}
        detail_str = ", ".join(f"{k}={v}" for k, v in list(details.items())[:3]) if details else ""
        table.add_row(
            r.get("run_type", ""),
            _status_style(r.get("status", "")),
            r.get("started_at", "")[:19],
            (r.get("ended_at") or "")[:19] or "[dim]--[/]",
            detail_str[:40] or "[dim]--[/]",
        )

    console.print(table)
