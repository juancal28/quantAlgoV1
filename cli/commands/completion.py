"""quant completion — install/show/uninstall shell tab completion (bash, zsh, powershell)."""

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

_PS_DIR = Path.home() / ".powershell_completions"
_PS_SCRIPT = _PS_DIR / "quant.ps1"

# PowerShell profile paths (PS 7+ and Windows PS 5.1).
_PS7_PROFILE = Path.home() / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
_PS5_PROFILE = Path.home() / "Documents" / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"


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

    # Match both "quant" and "quant.exe" for Windows Git Bash compatibility.
    return f"""\
# Bash completion for {_PROG} CLI (auto-generated)  {_MARKER}
_{_PROG}_completion() {{
    local cur prev
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    # Top-level commands (match both quant and quant.exe for Git Bash on Windows)
    if [[ "$prev" == "{_PROG}" || "$prev" == "{_PROG}.exe" ]]; then
        COMPREPLY=( $(compgen -W "{top_cmds}" -- "$cur") )
        return 0
    fi

    # Sub-group completions
    case "$prev" in
{case_block}
    esac
}}
complete -o default -F _{_PROG}_completion {_PROG} {_PROG}.exe
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


def _generate_powershell_script(tree: dict[str, list[str]]) -> str:
    top_cmds = ", ".join(f"'{n}'" for n in sorted(tree.keys()))

    sub_blocks: list[str] = []
    for group, subs in sorted(tree.items()):
        if subs:
            sub_list = ", ".join(f"'{s}'" for s in subs)
            sub_blocks.append(
                f"        '{group}' {{ $completions = @({sub_list}) }}"
            )

    sub_switch = "\n".join(sub_blocks)

    return f"""\
# PowerShell completion for {_PROG} CLI (auto-generated)  {_MARKER}
Register-ArgumentCompleter -CommandName {_PROG} -ScriptBlock {{
    param($wordToComplete, $commandAst, $cursorPosition)

    $tokens = $commandAst.ToString() -split '\\s+'

    if ($tokens.Count -le 2) {{
        $completions = @({top_cmds})
    }} else {{
        $sub = $tokens[1]
        $completions = @()
        switch ($sub) {{
{sub_switch}
        }}
    }}

    $completions | Where-Object {{ $_ -like "$wordToComplete*" }} | ForEach-Object {{
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
    }}
}}
"""


# --- RC file helpers -------------------------------------------------------

def _is_quant_completion_line(line: str) -> bool:
    lower = line.lower()
    return "quant" in lower and (
        "_complete" in lower
        or "bash_completions" in lower
        or ".zfunc" in lower
        or "powershell_completions" in lower
        or _MARKER.lower() in lower
    )


def _clean_rc(rc_file: Path) -> str:
    if not rc_file.exists():
        return ""
    lines = rc_file.read_text(encoding="utf-8").splitlines(keepends=True)
    return "".join(ln for ln in lines if not _is_quant_completion_line(ln))


def _detect_shell() -> str:
    """Detect the current shell, defaulting to powershell on Windows."""
    shell_path = os.environ.get("SHELL", "")
    if "zsh" in shell_path:
        return "zsh"
    if "bash" in shell_path:
        return "bash"
    # No $SHELL set — likely PowerShell on Windows.
    if os.name == "nt":
        return "powershell"
    return "bash"


# --- Install / uninstall per shell -----------------------------------------

def _add_source_line(rc_file: Path, source_line: str) -> None:
    """Ensure source_line is in rc_file, cleaning old quant lines first."""
    cleaned = _clean_rc(rc_file)
    if source_line not in cleaned:
        rc_file.parent.mkdir(parents=True, exist_ok=True)
        with open(rc_file, "w", encoding="utf-8") as f:
            f.write(cleaned)
            if cleaned and not cleaned.endswith("\n"):
                f.write("\n")
            f.write(f"\n{source_line}\n")
    elif cleaned != (rc_file.read_text(encoding="utf-8") if rc_file.exists() else ""):
        rc_file.write_text(cleaned, encoding="utf-8")


def _install_bash(tree: dict[str, list[str]]) -> None:
    _BASH_DIR.mkdir(parents=True, exist_ok=True)
    _BASH_SCRIPT.write_text(_generate_bash_script(tree), encoding="utf-8")

    source_line = f'source "{_BASH_SCRIPT.as_posix()}"  {_MARKER}'
    _add_source_line(_BASHRC, source_line)

    typer.echo(f"[bash] Script installed: {_BASH_SCRIPT.as_posix()}")
    typer.echo(f"[bash] Source line in:   {_BASHRC.as_posix()}")


def _install_zsh(tree: dict[str, list[str]]) -> None:
    _ZSH_DIR.mkdir(parents=True, exist_ok=True)
    _ZSH_SCRIPT.write_text(_generate_zsh_script(tree), encoding="utf-8")

    source_line = f'source "{_ZSH_SCRIPT.as_posix()}"  {_MARKER}'
    _add_source_line(_ZSHRC, source_line)

    typer.echo(f"[zsh]  Script installed: {_ZSH_SCRIPT.as_posix()}")
    typer.echo(f"[zsh]  Source line in:   {_ZSHRC.as_posix()}")


def _install_powershell(tree: dict[str, list[str]]) -> None:
    _PS_DIR.mkdir(parents=True, exist_ok=True)
    _PS_SCRIPT.write_text(_generate_powershell_script(tree), encoding="utf-8")

    # Use Windows backslash path for PowerShell dot-source.
    ps_path = str(_PS_SCRIPT)
    source_line = f'. "{ps_path}"  {_MARKER}'

    # Add to whichever PS profiles exist (or create the 5.1 profile).
    profiles_updated: list[Path] = []
    for profile in (_PS7_PROFILE, _PS5_PROFILE):
        if profile.parent.exists():
            _add_source_line(profile, source_line)
            profiles_updated.append(profile)

    if not profiles_updated:
        # Neither profile dir exists — create for Windows PS 5.1.
        _PS5_PROFILE.parent.mkdir(parents=True, exist_ok=True)
        _add_source_line(_PS5_PROFILE, source_line)
        profiles_updated.append(_PS5_PROFILE)

    typer.echo(f"[powershell] Script installed: {_PS_SCRIPT}")
    for p in profiles_updated:
        typer.echo(f"[powershell] Source line in:   {p}")


def _uninstall_shell(
    label: str, script: Path, rc_files: list[Path],
) -> None:
    if script.exists():
        script.unlink()
        typer.echo(f"[{label}] Removed: {script.as_posix()}")
    else:
        typer.echo(f"[{label}] Script not found (already removed).")

    for rc_file in rc_files:
        if rc_file.exists():
            original = rc_file.read_text(encoding="utf-8")
            cleaned = _clean_rc(rc_file)
            if cleaned != original:
                rc_file.write_text(cleaned, encoding="utf-8")
                typer.echo(f"[{label}] Source line removed from: {rc_file}")
            else:
                typer.echo(f"[{label}] No completion line in {rc_file.name}.")


# --- CLI commands -----------------------------------------------------------

_ALL_SHELLS = ["bash", "zsh", "powershell"]


def _resolve_shells(shell: str) -> list[str]:
    shell = shell.strip().lower()
    if shell == "all":
        return _ALL_SHELLS
    if shell in ("powershell", "pwsh", "ps"):
        return ["powershell"]
    if shell in ("bash", "zsh"):
        return [shell]
    if shell == "":
        return [_detect_shell()]
    typer.echo(f"Unknown shell '{shell}'. Supported: bash, zsh, powershell, all.")
    raise typer.Exit(1)


_INSTALLERS = {
    "bash": _install_bash,
    "zsh": _install_zsh,
    "powershell": _install_powershell,
}

_UNINSTALLERS = {
    "bash": ("bash", _BASH_SCRIPT, [_BASHRC]),
    "zsh": ("zsh", _ZSH_SCRIPT, [_ZSHRC]),
    "powershell": ("powershell", _PS_SCRIPT, [_PS7_PROFILE, _PS5_PROFILE]),
}

_GENERATORS = {
    "bash": _generate_bash_script,
    "zsh": _generate_zsh_script,
    "powershell": _generate_powershell_script,
}


@completion_app.command("install")
def install(
    shell: str = typer.Option(
        "", "--shell", "-s",
        help="Shell to install for: bash, zsh, powershell, or all. Auto-detects if omitted.",
    ),
) -> None:
    """Install tab-completion for the quant CLI."""
    tree = _get_command_tree()
    for sh in _resolve_shells(shell):
        _INSTALLERS[sh](tree)
    typer.echo("Restart your shell to activate.")


@completion_app.command("show")
def show(
    shell: str = typer.Option(
        "", "--shell", "-s",
        help="Shell variant: bash, zsh, or powershell. Auto-detects if omitted.",
    ),
) -> None:
    """Print the completion script to stdout (for manual install)."""
    tree = _get_command_tree()
    sh = _resolve_shells(shell)[0]
    typer.echo(_GENERATORS[sh](tree), nl=False)


@completion_app.command("uninstall")
def uninstall(
    shell: str = typer.Option(
        "", "--shell", "-s",
        help="Shell to uninstall for: bash, zsh, powershell, or all. Auto-detects if omitted.",
    ),
) -> None:
    """Remove tab-completion for the quant CLI."""
    for sh in _resolve_shells(shell):
        label, script, rc_files = _UNINSTALLERS[sh]
        _uninstall_shell(label, script, rc_files)
    typer.echo("Completion uninstalled. Restart your shell to take effect.")
