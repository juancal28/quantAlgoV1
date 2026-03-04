"""Rich view for pipeline runs."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from rich.console import Console
from rich.table import Table

_PST = timezone(timedelta(hours=-8), name="PST")


def _format_timestamp(ts: str | None) -> str:
    """Format an ISO timestamp into readable 'Mar 02  2:30 PM PST' style."""
    if not ts:
        return "[dim]--[/]"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        dt_pst = dt.astimezone(_PST)
        return dt_pst.strftime("%b %d  %I:%M %p").replace("  0", "   ")
    except (ValueError, AttributeError):
        return ts[:19]


def _status_style(status: str) -> str:
    if status == "ok":
        return f"[green]{status}[/]"
    if status == "fail":
        return f"[red]{status}[/]"
    if status == "running":
        return f"[yellow]{status}[/]"
    return status


def _brief_detail(details: dict[str, Any] | None) -> str:
    """Return the single most important detail for compact display (e.g. dashboard)."""
    if not details:
        return ""
    if "early_exit" in details:
        return str(details["early_exit"])
    if "error" in details:
        return str(details["error"])[:30]
    if details.get("skipped"):
        return details.get("reason", "lock_held")
    if "quality_score" in details:
        qp = details.get("quality_passed", False)
        if not qp:
            return "quality_failed"
        return "quality_passed"
    if "submitted_version_id" in details:
        return "submitted"
    if "ingested" in details:
        return f"ingested={details['ingested']}"
    if "confidence" in details:
        return f"conf={details['confidence']:.2f}"
    if "valid" in details:
        return "valid" if details["valid"] else "invalid"
    return ""


def _summarize_details(details: dict[str, Any]) -> str:
    """Build a human-readable summary from run details, prioritizing key fields."""
    if not details:
        return ""

    parts: list[str] = []

    # Early exit reason is the most important thing to show
    if "early_exit" in details:
        parts.append(f"[yellow]{details['early_exit']}[/]")

    # Error message for failed runs
    if "error" in details:
        err = str(details["error"])[:60]
        parts.append(f"[red]{err}[/]")

    # Skipped (singleton lock)
    if details.get("skipped"):
        reason = details.get("reason", "lock_held")
        parts.append(f"[dim]skipped ({reason})[/]")
        return ", ".join(parts)

    # Key metrics
    if "ingested" in details:
        parts.append(f"ingested={details['ingested']}")
    if "confidence" in details:
        parts.append(f"confidence={details['confidence']:.2f}")
    if "valid" in details:
        valid = details["valid"]
        parts.append(f"valid={'[green]yes[/]' if valid else '[red]no[/]'}")
    if "quality_score" in details:
        qs = details["quality_score"]
        qp = details.get("quality_passed", False)
        color = "green" if qp else "red"
        parts.append(f"quality=[{color}]{qs:.2f}[/]")
    # Backward compat: old runs with backtest data
    elif "in_sample_passed" in details:
        p = details["in_sample_passed"]
        parts.append(f"IS={'[green]pass[/]' if p else '[red]fail[/]'}")
        if "oos_passed" in details:
            p2 = details["oos_passed"]
            parts.append(f"OOS={'[green]pass[/]' if p2 else '[red]fail[/]'}")
    if "submitted_version_id" in details:
        vid = str(details["submitted_version_id"])[:8]
        parts.append(f"[green]submitted={vid}...[/]")

    # Agent name if present
    if "agent_name" in details:
        parts.append(f"agent={details['agent_name']}")

    return ", ".join(parts)


def render_runs(runs: list[dict[str, Any]], console: Console | None = None) -> None:
    console = console or Console()

    if not runs:
        console.print("[dim]No recent runs.[/]")
        return

    table = Table(title="Recent Runs")
    table.add_column("Type", width=16)
    table.add_column("Status", width=10)
    table.add_column("Started", style="dim", width=16)
    table.add_column("Ended", style="dim", width=16)
    table.add_column("Details", min_width=30, no_wrap=False)

    for r in runs:
        details = r.get("details") or {}
        detail_str = _summarize_details(details)
        table.add_row(
            r.get("run_type", ""),
            _status_style(r.get("status", "")),
            _format_timestamp(r.get("started_at")),
            _format_timestamp(r.get("ended_at")),
            detail_str or "[dim]--[/]",
        )

    console.print(table)
