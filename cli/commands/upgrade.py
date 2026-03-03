"""quant upgrade — pull latest changes and reinstall."""

from __future__ import annotations

import subprocess
import sys

import typer
from rich.console import Console


console = Console()


def upgrade() -> None:
    """Pull the latest changes from git and reinstall the package."""
    steps = [
        ("Pulling latest changes", ["git", "pull", "--ff-only"]),
        ("Installing updated package", [sys.executable, "-m", "pip", "install", "-e", ".[dev]", "--quiet"]),
    ]

    for label, cmd in steps:
        console.print(f"[bold cyan]{label}...[/]")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]Failed:[/] {result.stderr.strip() or result.stdout.strip()}")
            raise typer.Exit(1)
        if result.stdout.strip():
            console.print(f"  [dim]{result.stdout.strip()}[/]")

    console.print("[bold green]Upgrade complete.[/]")
