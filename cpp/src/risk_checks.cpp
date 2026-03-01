#include "quant_core/risk_checks.hpp"

namespace quant_core {

CircuitBreakerResult check_circuit_breaker(double realized_pnl, double unrealized_pnl,
                                           double peak_pnl, double initial_cash,
                                           double max_daily_loss_pct) {
    double total_pnl = realized_pnl + unrealized_pnl;

    if (total_pnl > peak_pnl) {
        peak_pnl = total_pnl;
    }

    double loss_pct = 0.0;
    if (initial_cash > 0.0) {
        loss_pct = -total_pnl / initial_cash;
    }

    bool tripped = loss_pct >= max_daily_loss_pct;

    return CircuitBreakerResult{tripped, peak_pnl, total_pnl, loss_pct};
}

bool check_exposure_limit(double gross_exposure, double portfolio_value,
                          double max_gross_exposure) {
    if (portfolio_value <= 0.0) {
        return gross_exposure <= 0.0;
    }
    double ratio = gross_exposure / portfolio_value;
    return ratio <= max_gross_exposure;
}

bool check_trade_rate_limit(int recent_order_count, int max_trades_per_hour) {
    return recent_order_count < max_trades_per_hour;
}

}  // namespace quant_core
