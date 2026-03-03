"""Scheduler pause/resume CLI commands."""

from __future__ import annotations

import typer

from cli import client

scheduler_app = typer.Typer(help="Pause or resume the scheduler.")


@scheduler_app.command("pause")
def pause() -> None:
    """Pause all scheduled tasks. No news cycles, trade ticks, or API calls will run."""
    result = client.post("/scheduler/pause")
    if result.get("paused"):
        typer.echo("Scheduler paused. No automated tasks will run until you resume.")
    else:
        typer.echo(f"Unexpected response: {result}")


@scheduler_app.command("resume")
def resume() -> None:
    """Resume all scheduled tasks."""
    result = client.post("/scheduler/resume")
    if not result.get("paused"):
        typer.echo("Scheduler resumed. Automated tasks will run on their normal schedule.")
    else:
        typer.echo(f"Unexpected response: {result}")


@scheduler_app.command("status")
def status() -> None:
    """Check whether the scheduler is paused or running."""
    result = client.get("/scheduler/status")
    if result.get("paused"):
        typer.echo("Scheduler is PAUSED. Run 'quant scheduler resume' to restart.")
    else:
        typer.echo("Scheduler is RUNNING.")
