#pragma once

#include "quant_core/order.hpp"
#include "quant_core/paper_broker.hpp"
#include "quant_core/types.hpp"

#include <string>
#include <unordered_map>
#include <vector>

namespace quant_core {

struct ReconcileResult {
    std::vector<std::string> to_buy;
    std::vector<std::string> to_sell;
};

/// Compare target signals vs held positions.
ReconcileResult reconcile_positions(
    const std::unordered_map<std::string, std::string>& signals,
    const std::unordered_map<std::string, double>& current_positions);

/// Orchestrate sells then buys through the C++ PaperBroker.
std::vector<Order> execute_signals(
    PaperBroker& broker,
    const std::unordered_map<std::string, std::string>& signals,
    const PriceMap& current_prices,
    int max_positions,
    double max_position_pct,
    bool circuit_breaker_tripped,
    double max_gross_exposure,
    int max_trades_per_hour);

}  // namespace quant_core
