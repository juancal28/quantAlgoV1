"""Approval gate logic.

Strategy proposals land in pending_approval status. Only an explicit
approval call (POST /strategies/{name}/approve/{version_id}) activates them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
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


async def approve_strategy(
    session: AsyncSession,
    strategy_name: str,
    version_id: str,
    approved_by: str = "human",
) -> StrategyVersion:
    """Approve a pending strategy version, making it active.

    1. Look up version by strategy name + id string
    2. Verify status is pending_approval
    3. Check daily activation limit
    4. Archive current active version (if any)
    5. Activate the pending version
    6. Write audit log

    Raises ValueError on any validation failure.
    """
    settings = get_settings()

    # 1. Look up version
    version = await strategy_repo.get_version_by_strategy_and_id(
        session, strategy_name, version_id
    )
    if version is None:
        raise ValueError(
            f"Version {version_id} not found for strategy {strategy_name!r}"
        )

    # 2. Verify pending_approval status
    if version.status != "pending_approval":
        raise ValueError(
            f"Version status is {version.status!r}, expected 'pending_approval'"
        )

    # 3. Check daily activation limit
    activations_today = await strategy_repo.count_activations_today(
        session, strategy_name
    )
    if activations_today >= settings.STRATEGY_MAX_ACTIVATIONS_PER_DAY:
        raise ValueError(
            f"Daily activation limit ({settings.STRATEGY_MAX_ACTIVATIONS_PER_DAY}) "
            f"reached for strategy {strategy_name!r}"
        )

    # 4. Archive current active version (if any)
    active = await strategy_repo.get_active_by_name(session, strategy_name)
    before_definition = None
    if active is not None:
        before_definition = active.definition
        active.status = "archived"
        await session.flush()

    # 5. Activate the pending version
    version.status = "active"
    version.approved_by = approved_by
    version.activated_at = datetime.now(timezone.utc)
    await session.flush()

    # 6. Write audit log
    changed_fields = []
    if before_definition and version.definition:
        all_keys = set(before_definition.keys()) | set(version.definition.keys())
        changed_fields = sorted(
            k for k in all_keys
            if before_definition.get(k) != version.definition.get(k)
        )

    audit = StrategyAuditLog(
        strategy_name=strategy_name,
        version_id=version.id,
        action="approved",
        trigger=approved_by,
        before_definition=before_definition,
        after_definition=version.definition,
        backtest_metrics=version.backtest_metrics,
        diff_fields=changed_fields,
    )
    session.add(audit)
    await session.flush()

    return version
