#include "quant_core/position_sizer.hpp"

#include <algorithm>

namespace quant_core {

double compute_order_quantity(double price, double portfolio_value, double cash_available,
                              int num_target_positions, double max_position_pct) {
    if (price <= 0.0 || portfolio_value <= 0.0 || cash_available <= 0.0 || num_target_positions <= 0) {
        return 0.0;
    }

    // Equal-weight target
    double target_value = portfolio_value / static_cast<double>(num_target_positions);

    // Cap at max position percentage
    double max_value = portfolio_value * max_position_pct;
    target_value = std::min(target_value, max_value);

    // Cap at available cash
    target_value = std::min(target_value, cash_available);

    if (target_value <= 0.0) {
        return 0.0;
    }

    return target_value / price;
}

}  // namespace quant_core
