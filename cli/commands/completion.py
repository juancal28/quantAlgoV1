"""quant completion — install/show/uninstall shell tab completion."""

from __future__ import annotations

import os
from pathlib import Path

import typer

completion_app = typer.Typer(help="Shell tab-completion management.")

_COMP_DIR = Path.home() / ".bash_completions"
_COMP_SCRIPT = _COMP_DIR / "quant.sh"
_BASHRC = Path.home() / ".bashrc"

# Source line uses forward-slash path for Git Bash robustness.
_SOURCE_LINE = f'source "{_COMP_SCRIPT.as_posix()}"  # quant CLI completion'


def _generate_completion_script() -> str:
    """Return the bash completion script for the quant CLI."""
    # Typer/Click use the pattern: _<UPPER_NAME>_COMPLETE=bash_source <prog>
    # The env var name is derived from the program name, uppercased, with
    # hyphens replaced by underscores.
    prog = "quant"
    env_var = f"_{prog.upper()}_COMPLETE"
    return (
        f'# Bash completion for {prog} CLI (auto-generated)\n'
        f'eval "$({env_var}=bash_source {prog})"\n'
    )


@completion_app.command("install")
def install() -> None:
    """Install bash tab-completion for the quant CLI."""
    _COMP_DIR.mkdir(parents=True, exist_ok=True)

    script = _generate_completion_script()
    _COMP_SCRIPT.write_text(script, encoding="utf-8")

    # Ensure .bashrc sources the completion script.
    needs_source_line = True
    if _BASHRC.exists():
        existing = _BASHRC.read_text(encoding="utf-8")
        # Remove any stale quant completion lines (e.g. from Typer --install-completion
        # with Windows backslash paths).
        cleaned_lines: list[str] = []
        for line in existing.splitlines(keepends=True):
            if "quant" in line.lower() and ("_complete" in line.lower() or "bash_completions" in line.lower()):
                continue  # drop old completion lines
            cleaned_lines.append(line)
        cleaned = "".join(cleaned_lines)

        if _SOURCE_LINE in cleaned:
            needs_source_line = False

        if cleaned != existing:
            _BASHRC.write_text(cleaned, encoding="utf-8")
    else:
        cleaned = ""

    if needs_source_line:
        with open(_BASHRC, "a", encoding="utf-8") as f:
            if cleaned and not cleaned.endswith("\n"):
                f.write("\n")
            f.write(f"\n{_SOURCE_LINE}\n")

    typer.echo(f"Completion script installed: {_COMP_SCRIPT.as_posix()}")
    typer.echo(f"Source line added to: {_BASHRC.as_posix()}")
    typer.echo("Restart your shell or run:  source ~/.bashrc")


@completion_app.command("show")
def show() -> None:
    """Print the completion script to stdout (for manual install)."""
    typer.echo(_generate_completion_script(), nl=False)


@completion_app.command("uninstall")
def uninstall() -> None:
    """Remove bash tab-completion for the quant CLI."""
    # Remove the completion script.
    if _COMP_SCRIPT.exists():
        _COMP_SCRIPT.unlink()
        typer.echo(f"Removed: {_COMP_SCRIPT.as_posix()}")
    else:
        typer.echo("Completion script not found (already removed).")

    # Remove the source line from .bashrc.
    if _BASHRC.exists():
        existing = _BASHRC.read_text(encoding="utf-8")
        cleaned_lines: list[str] = []
        for line in existing.splitlines(keepends=True):
            if "quant" in line.lower() and ("_complete" in line.lower() or "bash_completions" in line.lower()):
                continue
            cleaned_lines.append(line)
        cleaned = "".join(cleaned_lines)
        if cleaned != existing:
            _BASHRC.write_text(cleaned, encoding="utf-8")
            typer.echo(f"Source line removed from: {_BASHRC.as_posix()}")
        else:
            typer.echo("No completion source line found in .bashrc.")
    else:
        typer.echo(".bashrc not found.")

    typer.echo("Completion uninstalled. Restart your shell to take effect.")
