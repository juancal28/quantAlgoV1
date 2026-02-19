"""Backtest MCP tool — thin async wrapper around core.backtesting.engine."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from apps.mcp_server.schemas import BacktestMetricsOutput, RunBacktestInput, RunBacktestOutput
from core.backtesting.engine import run_backtest
from core.storage.models import MarketBar
from core.storage.repos import market_data_repo


def _bars_to_dataframe(bars: list[MarketBar]) -> pd.DataFrame:
    """Convert a list of MarketBar ORM objects to a pandas DataFrame indexed by bar_time."""
    records = []
    for b in bars:
        records.append({
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": int(b.volume),
        })
    index = [b.bar_time for b in bars]
    return pd.DataFrame(records, index=index)


async def run_backtest_tool(
    session: AsyncSession,
    params: RunBacktestInput,
) -> RunBacktestOutput:
    """Fetch market bars, run the backtest engine, and return results."""
    start_dt = datetime.fromisoformat(params.start)
    end_dt = datetime.fromisoformat(params.end)

    definition = params.definition_json
    universe = definition.get("universe", [])

    price_data: dict[str, pd.DataFrame] = {}
    for ticker in universe:
        bars = await market_data_repo.get_bars_in_range(
            session, ticker, start_dt, end_dt,
        )
        if not bars:
            raise ValueError(f"No market bars found for {ticker} between {params.start} and {params.end}")
        price_data[ticker] = _bars_to_dataframe(bars)

    result = run_backtest(definition, price_data)

    m = result.metrics
    return RunBacktestOutput(
        metrics=BacktestMetricsOutput(
            cagr=float(m.cagr),
            sharpe=float(m.sharpe),
            max_drawdown=float(m.max_drawdown),
            win_rate=float(m.win_rate),
            turnover=float(m.turnover),
            avg_trade_return=float(m.avg_trade_return),
        ),
        passed=result.passed,
        equity_curve_path=None,
    )
