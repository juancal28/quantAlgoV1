"""quant completion — install/show/uninstall shell tab completion (bash + zsh)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import typer

completion_app = typer.Typer(help="Shell tab-completion management.")

_PROG = "quant"
_ENV_VAR = f"_{_PROG.upper()}_COMPLETE"
_MARKER = "# quant CLI completion"


@dataclass
class _ShellConfig:
    name: str
    script_dir: Path
    script_name: str
    rc_file: Path
    source_env: str  # Click/Typer completion env value

    @property
    def script_path(self) -> Path:
        return self.script_dir / self.script_name

    def generate_script(self) -> str:
        return (
            f"# {self.name} completion for {_PROG} CLI (auto-generated)\n"
            f'eval "$({_ENV_VAR}={self.source_env} {_PROG})"\n'
        )

    def source_line(self) -> str:
        if self.name == "zsh":
            return f'source "{self.script_path.as_posix()}"  {_MARKER}'
        return f'source "{self.script_path.as_posix()}"  {_MARKER}'


_BASH = _ShellConfig(
    name="bash",
    script_dir=Path.home() / ".bash_completions",
    script_name="quant.sh",
    rc_file=Path.home() / ".bashrc",
    source_env="bash_source",
)

_ZSH = _ShellConfig(
    name="zsh",
    script_dir=Path.home() / ".zfunc",
    script_name="_quant",
    rc_file=Path.home() / ".zshrc",
    source_env="zsh_source",
)

_SHELLS = {"bash": _BASH, "zsh": _ZSH}


def _detect_shell() -> _ShellConfig:
    """Detect the current shell from $SHELL, fall back to bash."""
    shell_path = os.environ.get("SHELL", "")
    for name, cfg in _SHELLS.items():
        if name in shell_path:
            return cfg
    return _BASH


def _is_quant_completion_line(line: str) -> bool:
    """Return True if the line is a quant completion entry (old or new)."""
    lower = line.lower()
    return "quant" in lower and (
        "_complete" in lower or "bash_completions" in lower
        or ".zfunc" in lower or _MARKER.lower() in lower
    )


def _clean_rc(rc_file: Path) -> str:
    """Read rc_file, strip any old quant completion lines, return cleaned text."""
    if not rc_file.exists():
        return ""
    lines = rc_file.read_text(encoding="utf-8").splitlines(keepends=True)
    return "".join(l for l in lines if not _is_quant_completion_line(l))


def _install_for_shell(cfg: _ShellConfig) -> None:
    """Write completion script and add source line to the shell rc file."""
    cfg.script_dir.mkdir(parents=True, exist_ok=True)
    cfg.script_path.write_text(cfg.generate_script(), encoding="utf-8")

    source = cfg.source_line()
    cleaned = _clean_rc(cfg.rc_file)

    if source not in cleaned:
        with open(cfg.rc_file, "w", encoding="utf-8") as f:
            f.write(cleaned)
            if cleaned and not cleaned.endswith("\n"):
                f.write("\n")
            f.write(f"\n{source}\n")
    elif cleaned != (cfg.rc_file.read_text(encoding="utf-8") if cfg.rc_file.exists() else ""):
        # Old lines removed but new line already present — rewrite to clean up.
        cfg.rc_file.write_text(cleaned, encoding="utf-8")

    typer.echo(f"[{cfg.name}] Script installed: {cfg.script_path.as_posix()}")
    typer.echo(f"[{cfg.name}] Source line in:   {cfg.rc_file.as_posix()}")


def _uninstall_for_shell(cfg: _ShellConfig) -> None:
    """Remove completion script and source line for one shell."""
    if cfg.script_path.exists():
        cfg.script_path.unlink()
        typer.echo(f"[{cfg.name}] Removed: {cfg.script_path.as_posix()}")
    else:
        typer.echo(f"[{cfg.name}] Script not found (already removed).")

    if cfg.rc_file.exists():
        original = cfg.rc_file.read_text(encoding="utf-8")
        cleaned = _clean_rc(cfg.rc_file)
        if cleaned != original:
            cfg.rc_file.write_text(cleaned, encoding="utf-8")
            typer.echo(f"[{cfg.name}] Source line removed from: {cfg.rc_file.as_posix()}")
        else:
            typer.echo(f"[{cfg.name}] No completion line found in {cfg.rc_file.name}.")


@completion_app.command("install")
def install(
    shell: str = typer.Option(
        "", "--shell", "-s",
        help="Shell to install for: bash, zsh, or all. Auto-detects if omitted.",
    ),
) -> None:
    """Install tab-completion for the quant CLI."""
    targets = _resolve_targets(shell)
    for cfg in targets:
        _install_for_shell(cfg)
    typer.echo("Restart your shell (or source the rc file) to activate.")


@completion_app.command("show")
def show(
    shell: str = typer.Option(
        "", "--shell", "-s",
        help="Shell variant: bash or zsh. Auto-detects if omitted.",
    ),
) -> None:
    """Print the completion script to stdout (for manual install)."""
    cfg = _resolve_targets(shell)[0]
    typer.echo(cfg.generate_script(), nl=False)


@completion_app.command("uninstall")
def uninstall(
    shell: str = typer.Option(
        "", "--shell", "-s",
        help="Shell to uninstall for: bash, zsh, or all. Auto-detects if omitted.",
    ),
) -> None:
    """Remove tab-completion for the quant CLI."""
    targets = _resolve_targets(shell)
    for cfg in targets:
        _uninstall_for_shell(cfg)
    typer.echo("Completion uninstalled. Restart your shell to take effect.")


def _resolve_targets(shell: str) -> list[_ShellConfig]:
    """Turn --shell flag into a list of shell configs."""
    shell = shell.strip().lower()
    if shell == "all":
        return list(_SHELLS.values())
    if shell in _SHELLS:
        return [_SHELLS[shell]]
    if shell == "":
        return [_detect_shell()]
    typer.echo(f"Unknown shell '{shell}'. Supported: bash, zsh, all.")
    raise typer.Exit(1)
