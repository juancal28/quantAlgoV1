"""Position sizing logic — delegating to C++."""

from __future__ import annotations

from _quant_core import cpp_compute_order_quantity


def compute_order_quantity(
    ticker: str,
    price: float,
    portfolio_value: float,
    cash_available: float,
    num_target_positions: int,
    sizing_config: dict | None = None,
) -> float:
    """Compute the number of shares to buy for equal-weight sizing.

    Capped at RISK_MAX_POSITION_PCT of portfolio value.
    Returns 0.0 on edge cases (no cash, zero price, etc.).
    """
    from core.config import get_settings

    if price <= 0 or portfolio_value <= 0 or cash_available <= 0 or num_target_positions <= 0:
        return 0.0

    max_pos_pct = get_settings().RISK_MAX_POSITION_PCT
    if sizing_config:
        max_pos_pct = min(
            sizing_config.get("max_position_pct", max_pos_pct),
            max_pos_pct,
        )

    return cpp_compute_order_quantity(
        price, portfolio_value, cash_available, num_target_positions, max_pos_pct,
    )
