"""quant strategies — list and approve strategies."""

from __future__ import annotations

from typing import Optional

import typer

from cli import client
from cli.views.strategies_view import render_strategies, render_strategy_detail

strategies_app = typer.Typer(
    help="Strategy management.",
    invoke_without_command=True,
)


@strategies_app.callback()
def strategies_default(ctx: typer.Context) -> None:
    """List all strategies when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        data = client.get("/strategies")
        render_strategies(data)


@strategies_app.command("list")
def list_strategies(
    status: Optional[str] = typer.Option(None, "-s", "--status", help="Filter by status"),
) -> None:
    """List all strategies, optionally filtered by status."""
    params = {}
    if status:
        params["status"] = status
    data = client.get("/strategies", params=params)
    render_strategies(data)


@strategies_app.command("approve")
def approve_strategy(
    name: str = typer.Argument(..., help="Strategy name"),
    version_id: str = typer.Argument(..., help="Version ID to approve"),
) -> None:
    """Approve a pending strategy version."""
    # Fetch versions to show detail before confirming
    versions = client.get(f"/strategies/{name}/versions")
    target = next((v for v in versions if v.get("id") == version_id), None)
    if target:
        render_strategy_detail(target)
    else:
        typer.echo(f"Version {version_id} not found in fetched versions, proceeding anyway.")

    if not typer.confirm("Approve this strategy version?"):
        typer.echo("Cancelled.")
        raise typer.Exit()

    result = client.post(f"/strategies/{name}/approve/{version_id}")
    typer.echo(
        f"Approved: {result.get('strategy_version_id')} "
        f"[status={result.get('status')}, by={result.get('approved_by')}]"
    )


@strategies_app.command("deactivate")
def deactivate_strategy(
    name: str = typer.Argument(..., help="Strategy name to deactivate"),
) -> None:
    """Deactivate (archive) the active version of a strategy."""
    # Fetch active version to show detail before confirming
    try:
        active = client.get(f"/strategies/{name}/active")
        render_strategy_detail(active)
    except Exception:
        typer.echo(f"No active version found for {name!r}.")
        raise typer.Exit(code=1)

    if not typer.confirm("Deactivate this strategy?"):
        typer.echo("Cancelled.")
        raise typer.Exit()

    result = client.post(f"/strategies/{name}/deactivate")
    typer.echo(
        f"Deactivated: {result.get('strategy_version_id')} "
        f"[status={result.get('status')}, name={result.get('name')}]"
    )
