#include "quant_core/cost_model.hpp"

#include <cmath>

namespace quant_core {

double CostModel::apply_costs(double price, double quantity, const std::string& side) const {
    double impact_bps = slippage_bps + spread_bps / 2.0;
    if (side == "BUY") {
        return price * (1.0 + impact_bps / 10000.0);
    } else {
        return price * (1.0 - impact_bps / 10000.0);
    }
}

double CostModel::trade_commission() const {
    return commission_per_trade;
}

double CostModel::total_cost_for_trade(double price, double quantity, const std::string& side) const {
    double fill_price = apply_costs(price, quantity, side);
    double price_impact = std::abs(fill_price - price) * std::abs(quantity);
    return price_impact + commission_per_trade;
}

}  // namespace quant_core
