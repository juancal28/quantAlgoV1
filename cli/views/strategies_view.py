"""Rich view for strategies."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def _status_style(status: str) -> str:
    if status == "active":
        return f"[green]{status}[/]"
    if status == "pending_approval":
        return f"[yellow]{status}[/]"
    if status == "archived":
        return f"[dim]{status}[/]"
    return status


def render_strategies(strategies: list[dict[str, Any]], console: Console | None = None) -> None:
    console = console or Console()

    if not strategies:
        console.print("[dim]No strategies found.[/]")
        return

    table = Table(title="Strategies")
    table.add_column("Name", width=25)
    table.add_column("Version", justify="right", width=8)
    table.add_column("Status", width=18)
    table.add_column("Created", style="dim", width=20)
    table.add_column("Approved By", width=12)
    table.add_column("Quality", justify="right", width=8)

    for s in strategies:
        metrics = s.get("backtest_metrics") or {}
        # New quality-scored entries
        qs = metrics.get("quality_score")
        if qs and isinstance(qs, dict):
            composite = qs.get("composite")
            quality_text = f"{composite:.2f}" if composite is not None else "[dim]--[/]"
        else:
            # Backward compat: old entries with Sharpe
            sharpe = metrics.get("sharpe")
            quality_text = f"{sharpe:.2f}" if sharpe is not None else "[dim]--[/]"
        table.add_row(
            s.get("name", ""),
            str(s.get("version", "")),
            _status_style(s.get("status", "")),
            s.get("created_at", "")[:19],
            s.get("approved_by") or "[dim]--[/]",
            quality_text,
        )

    console.print(table)


def render_strategy_detail(s: dict[str, Any], console: Console | None = None) -> None:
    console = console or Console()

    lines = [
        f"[bold]Name:[/]     {s.get('name')}",
        f"[bold]Version:[/]  {s.get('version')}",
        f"[bold]Status:[/]   {_status_style(s.get('status', ''))}",
        f"[bold]Reason:[/]   {s.get('reason', '')}",
    ]
    metrics = s.get("backtest_metrics") or {}
    if metrics:
        lines.append("")
        qs = metrics.get("quality_score")
        if qs and isinstance(qs, dict):
            lines.append("[bold]Quality Score:[/]")
            composite = qs.get("composite", 0)
            passed = qs.get("passed", False)
            color = "green" if passed else "red"
            lines.append(f"  composite: [{color}]{composite:.4f}[/] ({'passed' if passed else 'failed'})")
            dims = qs.get("dimensions", {})
            for name, info in dims.items():
                lines.append(f"  {name}: {info.get('score', 0):.4f} (w={info.get('weight', 0)}) — {info.get('detail', '')}")
        else:
            # Backward compat: old backtest metrics
            lines.append("[bold]Backtest Metrics:[/]")
            for k, v in metrics.items():
                lines.append(f"  {k}: {v}")

    console.print(Panel("\n".join(lines), title="Strategy Detail", border_style="cyan"))
