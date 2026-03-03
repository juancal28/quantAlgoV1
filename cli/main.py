"""Quant CLI — terminal interface for the Quant News-RAG Trading System."""

from __future__ import annotations

import typer

from cli.commands.cycle import cycle
from cli.commands.dashboard import dashboard
from cli.commands.news import news
from cli.commands.pnl import pnl
from cli.commands.runs import runs
from cli.commands.status import status
from cli.commands.strategies import strategies_app
from cli.config import set_api_url

app = typer.Typer(
    name="quant",
    help="Terminal CLI for the Quant News-RAG Trading System.",
    no_args_is_help=True,
)

# Sub-groups
config_app = typer.Typer(help="CLI configuration.")
app.add_typer(config_app, name="config")
app.add_typer(strategies_app, name="strategies")

# Top-level commands
app.command()(status)
app.command()(news)
app.command()(runs)
app.command()(pnl)
app.command()(cycle)
app.command()(dashboard)


@config_app.command("set-url")
def config_set_url(url: str = typer.Argument(..., help="Railway API base URL")) -> None:
    """Save the API URL for all future commands."""
    set_api_url(url)
    typer.echo(f"API URL saved: {url}")


if __name__ == "__main__":
    app()
