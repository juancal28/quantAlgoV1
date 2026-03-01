#pragma once

namespace quant_core {

struct CircuitBreakerResult {
    bool tripped;
    double updated_peak_pnl;
    double total_pnl;
    double loss_pct;
};

/// Pure-math circuit breaker check — no DB involved.
CircuitBreakerResult check_circuit_breaker(double realized_pnl, double unrealized_pnl,
                                           double peak_pnl, double initial_cash,
                                           double max_daily_loss_pct);

/// Return true if gross exposure is within the allowed limit.
bool check_exposure_limit(double gross_exposure, double portfolio_value,
                          double max_gross_exposure);

/// Return true if recent order count is within the rate limit.
bool check_trade_rate_limit(int recent_order_count, int max_trades_per_hour);

}  // namespace quant_core
