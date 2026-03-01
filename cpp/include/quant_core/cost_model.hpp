#pragma once

#include <string>

namespace quant_core {

struct CostModel {
    double commission_per_trade;
    double slippage_bps;
    double spread_bps;

    /// Return the adjusted fill price after slippage and spread.
    /// BUY fills higher, SELL fills lower.
    double apply_costs(double price, double quantity, const std::string& side) const;

    /// Flat commission per trade.
    double trade_commission() const;

    /// Total dollar impact of a trade including commission (positive value).
    double total_cost_for_trade(double price, double quantity, const std::string& side) const;
};

}  // namespace quant_core
