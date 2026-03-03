"""Rich view for PnL snapshots."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

# Unicode block chars for sparkline (8 levels)
_BLOCKS = " " + "".join(chr(0x2581 + i) for i in range(7))


def _sparkline(values: list[float]) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo if hi != lo else 1.0
    return "".join(_BLOCKS[min(7, int((v - lo) / span * 7))] for v in values)


def _pnl_style(value: float) -> str:
    if value > 0:
        return f"[green]+{value:,.2f}[/]"
    if value < 0:
        return f"[red]{value:,.2f}[/]"
    return f"[dim]{value:,.2f}[/]"


def render_pnl(
    snapshots: list[dict[str, Any]],
    strategy_name: str,
    console: Console | None = None,
) -> None:
    console = console or Console()

    if not snapshots:
        console.print(f"[dim]No PnL data for {strategy_name!r}.[/]")
        return

    table = Table(title=f"PnL — {strategy_name}")
    table.add_column("Date", width=12)
    table.add_column("Realized", justify="right", width=14)
    table.add_column("Unrealized", justify="right", width=14)
    table.add_column("Exposure", justify="right", width=12)
    table.add_column("Peak", justify="right", width=14)

    for s in snapshots:
        table.add_row(
            s.get("date", ""),
            _pnl_style(s.get("realized_pnl", 0)),
            _pnl_style(s.get("unrealized_pnl", 0)),
            f"{s.get('gross_exposure', 0):,.2f}",
            _pnl_style(s.get("peak_pnl", 0)),
        )

    console.print(table)

    # Sparkline of realized PnL
    realized = [s.get("realized_pnl", 0) for s in snapshots]
    if realized:
        spark = _sparkline(realized)
        console.print(f"  Realized PnL trend: {spark}")
