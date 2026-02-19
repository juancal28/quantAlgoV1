"""Repository functions for pnl_snapshots table."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.storage.models import PnlSnapshot


async def get_snapshot(
    session: AsyncSession,
    strategy_name: str,
    snapshot_date: date,
) -> PnlSnapshot | None:
    """Fetch a single PnL snapshot for a strategy on a given date."""
    stmt = select(PnlSnapshot).where(
        PnlSnapshot.strategy_name == strategy_name,
        PnlSnapshot.snapshot_date == snapshot_date,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_snapshot(session: AsyncSession, snapshot: PnlSnapshot) -> PnlSnapshot:
    """Insert or update a PnL snapshot (conflict on strategy_name + date)."""
    values = {
        "id": snapshot.id,
        "strategy_name": snapshot.strategy_name,
        "snapshot_date": snapshot.snapshot_date,
        "realized_pnl": snapshot.realized_pnl,
        "unrealized_pnl": snapshot.unrealized_pnl,
        "gross_exposure": snapshot.gross_exposure,
        "peak_pnl": snapshot.peak_pnl,
        "positions": snapshot.positions,
        "created_at": snapshot.created_at,
    }
    stmt = pg_insert(PnlSnapshot).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["strategy_name", "snapshot_date"],
        set_={
            "realized_pnl": stmt.excluded.realized_pnl,
            "unrealized_pnl": stmt.excluded.unrealized_pnl,
            "gross_exposure": stmt.excluded.gross_exposure,
            "peak_pnl": stmt.excluded.peak_pnl,
            "positions": stmt.excluded.positions,
        },
    )
    await session.execute(stmt)
    await session.flush()
    return snapshot


async def get_daily_snapshots(
    session: AsyncSession,
    strategy_name: str,
    limit: int = 30,
) -> list[PnlSnapshot]:
    """Return the most recent PnL snapshots for a strategy."""
    stmt = (
        select(PnlSnapshot)
        .where(PnlSnapshot.strategy_name == strategy_name)
        .order_by(PnlSnapshot.snapshot_date.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
