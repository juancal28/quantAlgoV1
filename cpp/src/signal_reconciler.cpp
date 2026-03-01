#include "quant_core/signal_reconciler.hpp"
#include "quant_core/position_sizer.hpp"
#include "quant_core/risk_checks.hpp"

#include <algorithm>
#include <cmath>

namespace quant_core {

ReconcileResult reconcile_positions(
    const std::unordered_map<std::string, std::string>& signals,
    const std::unordered_map<std::string, double>& current_positions) {

    ReconcileResult result;

    // Tickers we want long but don't hold
    for (const auto& [ticker, direction] : signals) {
        if (direction == "long" && current_positions.find(ticker) == current_positions.end()) {
            result.to_buy.push_back(ticker);
        }
    }

    // Tickers we hold but should be flat
    for (const auto& [ticker, qty] : current_positions) {
        auto it = signals.find(ticker);
        std::string sig = (it != signals.end()) ? it->second : "flat";
        if (sig != "long") {
            result.to_sell.push_back(ticker);
        }
    }

    return result;
}

std::vector<Order> execute_signals(
    PaperBroker& broker,
    const std::unordered_map<std::string, std::string>& signals,
    const PriceMap& current_prices,
    int max_positions,
    double max_position_pct,
    bool circuit_breaker_tripped,
    double max_gross_exposure,
    int max_trades_per_hour) {

    std::vector<Order> orders;

    if (circuit_breaker_tripped) {
        return orders;
    }

    // Build current positions map
    std::unordered_map<std::string, double> current_pos;
    for (const auto& pos : broker.get_positions()) {
        current_pos[pos.ticker] = pos.quantity;
    }

    auto reconciled = reconcile_positions(signals, current_pos);

    if (reconciled.to_buy.empty() && reconciled.to_sell.empty()) {
        return orders;
    }

    // Check trade rate limit
    int recent_order_count = static_cast<int>(broker.get_orders().size());
    if (!check_trade_rate_limit(recent_order_count, max_trades_per_hour)) {
        return orders;
    }

    // Execute SELLs first to free up cash
    for (const auto& ticker : reconciled.to_sell) {
        auto pos_it = current_pos.find(ticker);
        if (pos_it == current_pos.end() || pos_it->second <= 0.0) {
            continue;
        }
        auto price_it = current_prices.find(ticker);
        if (price_it == current_prices.end() || price_it->second <= 0.0) {
            continue;
        }
        Order order = broker.submit_order(ticker, "SELL", pos_it->second, price_it->second);
        orders.push_back(order);
    }

    // Recalculate after sells
    double portfolio_value = broker.get_portfolio_value(current_prices);
    double cash = broker.get_cash();
    double exposure = broker.gross_exposure(current_prices);

    // Check exposure limit before buying
    if (!check_exposure_limit(exposure, portfolio_value, max_gross_exposure)) {
        return orders;
    }

    // Determine how many positions we can add
    int positions_after_sells = static_cast<int>(broker.get_positions().size());
    int buy_slots = std::max(0, max_positions - positions_after_sells);

    if (buy_slots == 0) {
        return orders;
    }

    // Limit buys to available slots
    int num_buys = std::min(static_cast<int>(reconciled.to_buy.size()), buy_slots);
    int num_target = std::max(num_buys, 1);

    for (int i = 0; i < num_buys; ++i) {
        const auto& ticker = reconciled.to_buy[i];
        auto price_it = current_prices.find(ticker);
        if (price_it == current_prices.end() || price_it->second <= 0.0) {
            continue;
        }
        double price = price_it->second;

        double qty_float = compute_order_quantity(
            price, portfolio_value, cash, num_target, max_position_pct);

        // Whole shares only (floor)
        int qty = static_cast<int>(std::floor(qty_float));
        if (qty <= 0) {
            continue;
        }

        Order order = broker.submit_order(ticker, "BUY", static_cast<double>(qty), price);
        orders.push_back(order);

        // Update cash after buy for subsequent iterations
        if (order.status == "filled") {
            cash = broker.get_cash();
        }
    }

    return orders;
}

}  // namespace quant_core
