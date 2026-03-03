"""quant completion — install/show/uninstall shell tab completion (bash + zsh)."""

from __future__ import annotations

import os
from pathlib import Path

import click
import typer

completion_app = typer.Typer(help="Shell tab-completion management.")

_PROG = "quant"
_MARKER = "# quant CLI completion"

# --- Shell paths -----------------------------------------------------------

_BASH_DIR = Path.home() / ".bash_completions"
_BASH_SCRIPT = _BASH_DIR / "quant.sh"
_BASHRC = Path.home() / ".bashrc"

_ZSH_DIR = Path.home() / ".zfunc"
_ZSH_SCRIPT = _ZSH_DIR / "_quant"
_ZSHRC = Path.home() / ".zshrc"


# --- Introspect the Typer app to discover commands -------------------------

def _get_command_tree() -> dict[str, list[str]]:
    """Return {command_name: [subcommands]} by introspecting the CLI app.

    Top-level commands have an empty list.  Sub-groups (like ``strategies``,
    ``config``, ``completion``) have their child command names listed.
    """
    # Late import to avoid circular dependency (main.py imports us).
    from cli.main import app as typer_app

    click_app = typer.main.get_command(typer_app)
    ctx = click.Context(click_app)
    tree: dict[str, list[str]] = {}

    for name in click_app.list_commands(ctx):
        cmd = click_app.get_command(ctx, name)
        if isinstance(cmd, click.MultiCommand):
            sub_ctx = click.Context(cmd, parent=ctx)
            tree[name] = list(cmd.list_commands(sub_ctx))
        else:
            tree[name] = []

    return tree


# --- Script generators -----------------------------------------------------

def _generate_bash_script(tree: dict[str, list[str]]) -> str:
    top_cmds = " ".join(sorted(tree.keys()))

    case_arms: list[str] = []
    for group, subs in sorted(tree.items()):
        if subs:
            sub_str = " ".join(subs)
            case_arms.append(
                f"        {group})\n"
                f'            COMPREPLY=( $(compgen -W "{sub_str}" -- "$cur") )\n'
                f"            return 0\n"
                f"            ;;"
            )

    case_block = "\n".join(case_arms)

    return f"""\
# Bash completion for {_PROG} CLI (auto-generated)  {_MARKER}
_{_PROG}_completion() {{
    local cur prev
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    # Top-level commands
    if [[ "$prev" == "{_PROG}" ]]; then
        COMPREPLY=( $(compgen -W "{top_cmds}" -- "$cur") )
        return 0
    fi

    # Sub-group completions
    case "$prev" in
{case_block}
    esac
}}
complete -o default -F _{_PROG}_completion {_PROG}
"""


def _generate_zsh_script(tree: dict[str, list[str]]) -> str:
    top_entries: list[str] = []
    for name in sorted(tree.keys()):
        top_entries.append(f"            '{name}'")
    top_block = "\n".join(top_entries)

    case_arms: list[str] = []
    for group, subs in sorted(tree.items()):
        if subs:
            sub_entries = "\n".join(f"                '{s}'" for s in subs)
            case_arms.append(
                f"            {group})\n"
                f"                subcommands=(\n"
                f"{sub_entries}\n"
                f"                )\n"
                f"                _describe 'subcommand' subcommands\n"
                f"                ;;"
            )

    case_block = "\n".join(case_arms)

    return f"""\
#compdef {_PROG}
# Zsh completion for {_PROG} CLI (auto-generated)  {_MARKER}

_{_PROG}() {{
    local -a commands subcommands

    if (( CURRENT == 2 )); then
        commands=(
{top_block}
        )
        _describe 'command' commands
    elif (( CURRENT == 3 )); then
        case "${{words[2]}}" in
{case_block}
        esac
    fi
}}

compdef _{_PROG} {_PROG}
"""


# --- RC file helpers -------------------------------------------------------

def _is_quant_completion_line(line: str) -> bool:
    lower = line.lower()
    return "quant" in lower and (
        "_complete" in lower
        or "bash_completions" in lower
        or ".zfunc" in lower
        or _MARKER.lower() in lower
    )


def _clean_rc(rc_file: Path) -> str:
    if not rc_file.exists():
        return ""
    lines = rc_file.read_text(encoding="utf-8").splitlines(keepends=True)
    return "".join(ln for ln in lines if not _is_quant_completion_line(ln))


def _detect_shell() -> str:
    shell_path = os.environ.get("SHELL", "")
    if "zsh" in shell_path:
        return "zsh"
    return "bash"


# --- Install / uninstall per shell -----------------------------------------

def _install_bash(tree: dict[str, list[str]]) -> None:
    _BASH_DIR.mkdir(parents=True, exist_ok=True)
    _BASH_SCRIPT.write_text(_generate_bash_script(tree), encoding="utf-8")

    source_line = f'source "{_BASH_SCRIPT.as_posix()}"  {_MARKER}'
    cleaned = _clean_rc(_BASHRC)

    if source_line not in cleaned:
        with open(_BASHRC, "w", encoding="utf-8") as f:
            f.write(cleaned)
            if cleaned and not cleaned.endswith("\n"):
                f.write("\n")
            f.write(f"\n{source_line}\n")
    elif cleaned != (_BASHRC.read_text(encoding="utf-8") if _BASHRC.exists() else ""):
        _BASHRC.write_text(cleaned, encoding="utf-8")

    typer.echo(f"[bash] Script installed: {_BASH_SCRIPT.as_posix()}")
    typer.echo(f"[bash] Source line in:   {_BASHRC.as_posix()}")


def _install_zsh(tree: dict[str, list[str]]) -> None:
    _ZSH_DIR.mkdir(parents=True, exist_ok=True)
    _ZSH_SCRIPT.write_text(_generate_zsh_script(tree), encoding="utf-8")

    source_line = f'source "{_ZSH_SCRIPT.as_posix()}"  {_MARKER}'
    cleaned = _clean_rc(_ZSHRC)

    if source_line not in cleaned:
        with open(_ZSHRC, "w", encoding="utf-8") as f:
            f.write(cleaned)
            if cleaned and not cleaned.endswith("\n"):
                f.write("\n")
            f.write(f"\n{source_line}\n")
    elif cleaned != (_ZSHRC.read_text(encoding="utf-8") if _ZSHRC.exists() else ""):
        _ZSHRC.write_text(cleaned, encoding="utf-8")

    typer.echo(f"[zsh]  Script installed: {_ZSH_SCRIPT.as_posix()}")
    typer.echo(f"[zsh]  Source line in:   {_ZSHRC.as_posix()}")


def _uninstall_shell(
    label: str, script: Path, rc_file: Path,
) -> None:
    if script.exists():
        script.unlink()
        typer.echo(f"[{label}] Removed: {script.as_posix()}")
    else:
        typer.echo(f"[{label}] Script not found (already removed).")

    if rc_file.exists():
        original = rc_file.read_text(encoding="utf-8")
        cleaned = _clean_rc(rc_file)
        if cleaned != original:
            rc_file.write_text(cleaned, encoding="utf-8")
            typer.echo(f"[{label}] Source line removed from: {rc_file.as_posix()}")
        else:
            typer.echo(f"[{label}] No completion line in {rc_file.name}.")


# --- CLI commands -----------------------------------------------------------

def _resolve_shells(shell: str) -> list[str]:
    shell = shell.strip().lower()
    if shell == "all":
        return ["bash", "zsh"]
    if shell in ("bash", "zsh"):
        return [shell]
    if shell == "":
        return [_detect_shell()]
    typer.echo(f"Unknown shell '{shell}'. Supported: bash, zsh, all.")
    raise typer.Exit(1)


@completion_app.command("install")
def install(
    shell: str = typer.Option(
        "", "--shell", "-s",
        help="Shell to install for: bash, zsh, or all. Auto-detects if omitted.",
    ),
) -> None:
    """Install tab-completion for the quant CLI."""
    tree = _get_command_tree()
    for sh in _resolve_shells(shell):
        if sh == "bash":
            _install_bash(tree)
        else:
            _install_zsh(tree)
    typer.echo("Restart your shell (or source the rc file) to activate.")


@completion_app.command("show")
def show(
    shell: str = typer.Option(
        "", "--shell", "-s",
        help="Shell variant: bash or zsh. Auto-detects if omitted.",
    ),
) -> None:
    """Print the completion script to stdout (for manual install)."""
    tree = _get_command_tree()
    sh = _resolve_shells(shell)[0]
    if sh == "bash":
        typer.echo(_generate_bash_script(tree), nl=False)
    else:
        typer.echo(_generate_zsh_script(tree), nl=False)


@completion_app.command("uninstall")
def uninstall(
    shell: str = typer.Option(
        "", "--shell", "-s",
        help="Shell to uninstall for: bash, zsh, or all. Auto-detects if omitted.",
    ),
) -> None:
    """Remove tab-completion for the quant CLI."""
    for sh in _resolve_shells(shell):
        if sh == "bash":
            _uninstall_shell("bash", _BASH_SCRIPT, _BASHRC)
        else:
            _uninstall_shell("zsh", _ZSH_SCRIPT, _ZSHRC)
    typer.echo("Completion uninstalled. Restart your shell to take effect.")
