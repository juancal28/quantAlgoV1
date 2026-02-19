"""Approval gate logic.

Strategy proposals land in pending_approval status. Only an explicit
approval call (POST /strategies/{name}/approve/{version_id}) activates them.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.storage.models import StrategyAuditLog, StrategyVersion
from core.storage.repos import strategy_repo


async def submit_for_approval(
    session: AsyncSession,
    strategy_name: str,
    definition: dict,
    reason: str,
    backtest_metrics: dict[str, Any] | None = None,
    trigger: str = "agent",
) -> StrategyVersion:
    """Create a new strategy version with status=pending_approval.

    NEVER sets status to 'active'. Writes an audit log entry with
    action='proposed'.

    Returns the created StrategyVersion.
    """
    # 1. Compute next version number
    existing = await strategy_repo.get_versions_by_name(session, strategy_name)
    next_version = (existing[0].version + 1) if existing else 1

    # 2. Get current active definition for audit log before_definition
    active = await strategy_repo.get_active_by_name(session, strategy_name)
    before_definition = active.definition if active else None

    # 3. Create version — status is ALWAYS pending_approval
    version = StrategyVersion(
        name=strategy_name,
        version=next_version,
        status="pending_approval",
        definition=definition,
        reason=reason,
        backtest_metrics=backtest_metrics,
    )
    await strategy_repo.create_version(session, version)

    # 4. Write audit log
    # Compute changed fields for audit
    changed_fields = []
    if before_definition:
        all_keys = set(before_definition.keys()) | set(definition.keys())
        changed_fields = sorted(
            k for k in all_keys if before_definition.get(k) != definition.get(k)
        )

    audit = StrategyAuditLog(
        strategy_name=strategy_name,
        version_id=version.id,
        action="proposed",
        trigger=trigger,
        before_definition=before_definition,
        after_definition=definition,
        backtest_metrics=backtest_metrics,
        diff_fields=changed_fields,
    )
    session.add(audit)
    await session.flush()

    return version
