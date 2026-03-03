"""Quant CLI — terminal interface for the Quant News-RAG Trading System."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cli.commands.completion import completion_app
from cli.commands.cycle import cycle
from cli.commands.dashboard import dashboard
from cli.commands.news import news
from cli.commands.pnl import pnl
from cli.commands.runs import runs
from cli.commands.status import status
from cli.commands.strategies import strategies_app
from cli.commands.upgrade import upgrade
from cli.config import CONFIG_FILE, get_api_url, set_api_url

app = typer.Typer(
    name="quant",
    help="Terminal CLI for the Quant News-RAG Trading System.",
    no_args_is_help=True,
    add_completion=False,
)

# Sub-groups
config_app = typer.Typer(help="CLI configuration.")
app.add_typer(completion_app, name="completion")
app.add_typer(config_app, name="config")
app.add_typer(strategies_app, name="strategies")

# Top-level commands
app.command()(status)
app.command()(news)
app.command()(runs)
app.command()(pnl)
app.command()(cycle)
app.command()(dashboard)
app.command()(upgrade)


@app.command()
def help() -> None:
    """Show all commands, usage examples, and current configuration."""
    console = Console()

    # --- Commands table ---
    table = Table(show_header=True, title="Commands", border_style="blue", padding=(0, 2))
    table.add_column("Command", style="bold cyan", width=38)
    table.add_column("Description")

    commands = [
        ("quant help", "Show this help page"),
        ("quant status", "System health: trading mode, market, services, strategy counts"),
        ("quant news [-m MINS] [-n LIMIT]", "Recent news articles with sentiment scores"),
        ("quant strategies list [-s STATUS]", "List strategies (filter: active, pending_approval, archived)"),
        ("quant strategies approve NAME ID", "Approve a pending strategy version (with confirmation)"),
        ("quant runs [-n LIMIT]", "Recent pipeline runs (ingest, backtest, etc.)"),
        ("quant pnl STRATEGY [-d DAYS]", "Daily PnL snapshots with sparkline"),
        ("quant cycle", "Trigger a manual news cycle"),
        ("quant dashboard [-i SECS]", "Live auto-refreshing dashboard (Ctrl+C to exit)"),
        ("quant upgrade", "Pull latest changes from git and reinstall"),
        ("quant config set-url URL", "Save the Railway API URL"),
        ("quant completion install [-s SHELL]", "Install tab-completion (bash/zsh/all, auto-detects)"),
        ("quant completion show [-s SHELL]", "Print completion script to stdout"),
        ("quant completion uninstall [-s SHELL]", "Remove tab-completion"),
    ]

    for cmd, desc in commands:
        table.add_row(cmd, desc)

    console.print(table)

    # --- Examples ---
    examples = Table(show_header=True, title="Examples", border_style="green", padding=(0, 2))
    examples.add_column("What you want", style="dim")
    examples.add_column("Command", style="bold")

    examples.add_row("Connect to your Railway API", "quant config set-url https://api.up.railway.app")
    examples.add_row("Check if everything is healthy", "quant status")
    examples.add_row("See news from the last hour", "quant news -m 60")
    examples.add_row("Find strategies waiting for approval", "quant strategies list -s pending_approval")
    examples.add_row("Approve a strategy", "quant strategies approve sentiment_v1 <version-id>")
    examples.add_row("Trigger a full pipeline run", "quant cycle")
    examples.add_row("Watch everything in real time", "quant dashboard -i 10")
    examples.add_row("Check PnL for last 7 days", "quant pnl sentiment_v1 -d 7")

    console.print()
    console.print(examples)

    # --- Current config ---
    console.print()
    try:
        url = get_api_url()
        config_line = f"[green]{url}[/]"
    except SystemExit:
        config_line = "[red]Not configured[/]"

    console.print(
        Panel(
            f"  API URL:     {config_line}\n"
            f"  Config file: [dim]{CONFIG_FILE}[/]\n"
            f"  Env var:     [dim]QUANT_API_URL[/]  (overrides config file if set)",
            title="Configuration",
            border_style="yellow",
        )
    )


@config_app.command("set-url")
def config_set_url(url: str = typer.Argument(..., help="Railway API base URL")) -> None:
    """Save the API URL for all future commands."""
    set_api_url(url)
    typer.echo(f"API URL saved: {url}")


if __name__ == "__main__":
    app()
