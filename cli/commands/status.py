"""quant status — system health panel."""

from __future__ import annotations

import typer

from cli import client
from cli.views.status_view import render_status


def status() -> None:
    """Show system health: trading mode, market status, services, strategy counts."""
    data = client.get("/status")
    render_status(data)
