"""quant ml-deps-update — trigger ML dependency update on the persistent volume."""

from __future__ import annotations

import typer

from cli import client


def ml_deps_update() -> None:
    """Update torch, transformers, and FinBERT model on the persistent volume."""
    typer.echo("Dispatching ML dependency update...")
    result = client.post("/ml-deps/update")
    status = result.get("status", "unknown")
    task_id = result.get("task_id", "?")
    if status == "dispatched":
        typer.echo(f"ML deps update dispatched (task_id={task_id}).")
        typer.echo("This runs in the background via Celery. Check worker logs for progress.")
    else:
        typer.echo(f"ML deps update failed to dispatch (status={status}).")
