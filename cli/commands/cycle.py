"""quant cycle — trigger a manual news cycle."""

from __future__ import annotations

import typer

from cli import client


def cycle() -> None:
    """Trigger a manual news cycle (ingest -> embed -> sentiment -> agent -> backtest)."""
    typer.echo("Dispatching news cycle...")
    result = client.post("/runs/news_cycle")
    status = result.get("status", "unknown")
    run_id = result.get("run_id", "?")
    if status == "dispatched":
        typer.echo(f"News cycle dispatched (run_id={run_id}). Track with: quant runs")
    else:
        typer.echo(f"News cycle failed to dispatch (status={status}, run_id={run_id})")
