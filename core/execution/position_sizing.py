"""Position sizing logic."""

from __future__ import annotations


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

    # Equal-weight target
    target_value = portfolio_value / num_target_positions

    # Cap at max position percentage
    max_value = portfolio_value * max_pos_pct
    target_value = min(target_value, max_value)

    # Cap at available cash
    target_value = min(target_value, cash_available)

    if target_value <= 0:
        return 0.0

    return target_value / price
