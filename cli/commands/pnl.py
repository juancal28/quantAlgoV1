"""quant pnl — daily PnL for a strategy."""

from __future__ import annotations

import typer

from cli import client
from cli.views.pnl_view import render_pnl


def pnl(
    strategy: str = typer.Argument(..., help="Strategy name"),
    days: int = typer.Option(30, "-d", "--days", help="Number of days to show"),
) -> None:
    """Show daily PnL snapshots for a strategy."""
    data = client.get("/pnl/daily", params={"strategy": strategy, "days": days})
    render_pnl(data, strategy_name=strategy)
