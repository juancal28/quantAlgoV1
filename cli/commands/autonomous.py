"""Autonomous mode CLI commands."""

from __future__ import annotations

import typer

from cli import client

autonomous_app = typer.Typer(help="Enable or disable fully autonomous trading.")


@autonomous_app.command("enable")
def enable() -> None:
    """Enable autonomous mode: auto-approve strategies and trade without human input."""
    typer.confirm(
        "This will enable fully autonomous mode.\n"
        "Strategies will be auto-approved and traded without your input.\n"
        "Continue?",
        abort=True,
    )
    result = client.post("/autonomous/enable")
    if result.get("enabled"):
        typer.echo("Autonomous mode ENABLED. Strategies will be auto-approved and traded.")
    else:
        typer.echo(f"Unexpected response: {result}")


@autonomous_app.command("disable")
def disable() -> None:
    """Disable autonomous mode: require manual approval for strategies."""
    result = client.post("/autonomous/disable")
    if not result.get("enabled"):
        typer.echo("Autonomous mode DISABLED. Strategies require manual approval.")
    else:
        typer.echo(f"Unexpected response: {result}")


@autonomous_app.command("status")
def status() -> None:
    """Check whether autonomous mode is enabled."""
    result = client.get("/autonomous/status")
    if result.get("enabled"):
        typer.echo("Autonomous mode is ENABLED. Strategies are auto-approved and traded.")
    else:
        typer.echo("Autonomous mode is DISABLED. Strategies require manual approval.")
