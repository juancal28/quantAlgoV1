#pragma once

#include "quant_core/cost_model.hpp"
#include "quant_core/order.hpp"
#include "quant_core/position.hpp"
#include "quant_core/types.hpp"

#include <string>
#include <unordered_map>
#include <vector>

namespace quant_core {

class PaperBroker {
public:
    PaperBroker(double initial_cash, CostModel cost_model);

    Order submit_order(const std::string& ticker, const std::string& side,
                       double qty, double price);

    std::vector<Position> get_positions() const;
    double get_cash() const;
    double get_portfolio_value(const PriceMap& prices) const;
    std::vector<Order> get_orders() const;
    double realized_pnl() const;
    double unrealized_pnl(const PriceMap& prices) const;
    double gross_exposure(const PriceMap& prices) const;

    // Access to internal cost model for signal reconciler
    const CostModel& cost_model() const { return cost_model_; }

private:
    struct PosEntry {
        double quantity;
        double avg_entry_price;
    };

    double cash_;
    CostModel cost_model_;
    std::unordered_map<std::string, PosEntry> positions_;
    std::vector<Order> orders_;
    double realized_pnl_ = 0.0;
};

}  // namespace quant_core
