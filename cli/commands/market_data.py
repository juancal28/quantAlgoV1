"""quant market-data — trigger market data ingestion."""

from __future__ import annotations

import typer

from cli import client


def market_data() -> None:
    """Fetch and store market bars for the approved universe (backfill)."""
    typer.echo("Dispatching market data ingestion...")
    result = client.post("/runs/market_data_ingest")
    status = result.get("status", "unknown")
    if status == "dispatched":
        typer.echo("Market data ingest dispatched. Track with: quant runs")
    else:
        typer.echo(f"Market data ingest failed to dispatch (status={status})")
