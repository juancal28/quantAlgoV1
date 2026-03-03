"""quant runs — recent pipeline runs."""

from __future__ import annotations

import typer

from cli import client
from cli.views.runs_view import render_runs


def runs(
    limit: int = typer.Option(20, "-n", "--limit", help="Max runs to show"),
) -> None:
    """Show recent pipeline runs."""
    data = client.get("/runs/recent", params={"limit": limit})
    render_runs(data)
