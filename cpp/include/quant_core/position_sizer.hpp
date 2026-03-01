#pragma once

namespace quant_core {

/// Compute order quantity for equal-weight sizing, capped at max_position_pct.
double compute_order_quantity(double price, double portfolio_value, double cash_available,
                              int num_target_positions, double max_position_pct);

}  // namespace quant_core
