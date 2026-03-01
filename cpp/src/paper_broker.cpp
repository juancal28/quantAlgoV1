#include "quant_core/paper_broker.hpp"

#include <cmath>

namespace quant_core {

PaperBroker::PaperBroker(double initial_cash, CostModel cost_model)
    : cash_(initial_cash), cost_model_(cost_model) {}

Order PaperBroker::submit_order(const std::string& ticker, const std::string& side,
                                double qty, double price) {
    double fill_price = cost_model_.apply_costs(price, qty, side);
    double commission = cost_model_.trade_commission();

    if (side == "BUY") {
        double total_cost = fill_price * qty + commission;
        if (total_cost > cash_) {
            Order order{ticker, side, qty, fill_price, "rejected"};
            orders_.push_back(order);
            return order;
        }

        cash_ -= total_cost;

        auto it = positions_.find(ticker);
        if (it != positions_.end()) {
            double old_qty = it->second.quantity;
            double old_avg = it->second.avg_entry_price;
            double new_qty = old_qty + qty;
            it->second.avg_entry_price = (old_avg * old_qty + fill_price * qty) / new_qty;
            it->second.quantity = new_qty;
        } else {
            positions_[ticker] = PosEntry{qty, fill_price};
        }

    } else if (side == "SELL") {
        auto it = positions_.find(ticker);
        if (it == positions_.end() || it->second.quantity < qty) {
            Order order{ticker, side, qty, fill_price, "rejected"};
            orders_.push_back(order);
            return order;
        }

        double proceeds = fill_price * qty - commission;
        cash_ += proceeds;

        double trade_pnl = (fill_price - it->second.avg_entry_price) * qty - commission;
        realized_pnl_ += trade_pnl;

        it->second.quantity -= qty;
        if (it->second.quantity <= 1e-9) {
            positions_.erase(it);
        }
    }

    Order order{ticker, side, qty, fill_price, "filled"};
    orders_.push_back(order);
    return order;
}

std::vector<Position> PaperBroker::get_positions() const {
    std::vector<Position> result;
    result.reserve(positions_.size());
    for (const auto& [ticker, pos] : positions_) {
        result.push_back(Position{ticker, pos.quantity, pos.avg_entry_price});
    }
    return result;
}

double PaperBroker::get_cash() const {
    return cash_;
}

double PaperBroker::get_portfolio_value(const PriceMap& prices) const {
    double value = cash_;
    for (const auto& [ticker, pos] : positions_) {
        auto it = prices.find(ticker);
        double price = (it != prices.end()) ? it->second : pos.avg_entry_price;
        value += pos.quantity * price;
    }
    return value;
}

std::vector<Order> PaperBroker::get_orders() const {
    return orders_;
}

double PaperBroker::realized_pnl() const {
    return realized_pnl_;
}

double PaperBroker::unrealized_pnl(const PriceMap& prices) const {
    double total = 0.0;
    for (const auto& [ticker, pos] : positions_) {
        auto it = prices.find(ticker);
        double price = (it != prices.end()) ? it->second : pos.avg_entry_price;
        total += (price - pos.avg_entry_price) * pos.quantity;
    }
    return total;
}

double PaperBroker::gross_exposure(const PriceMap& prices) const {
    double total = 0.0;
    for (const auto& [ticker, pos] : positions_) {
        auto it = prices.find(ticker);
        double price = (it != prices.end()) ? it->second : pos.avg_entry_price;
        total += std::abs(pos.quantity * price);
    }
    return total;
}

}  // namespace quant_core
