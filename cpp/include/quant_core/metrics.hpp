#pragma once

#include <vector>

namespace quant_core {

struct BacktestMetrics {
    double cagr;
    double sharpe;
    double max_drawdown;
    double win_rate;
    double turnover;
    double avg_trade_return;
};

/// Compute all 6 performance metrics from equity values and trade returns.
BacktestMetrics compute_metrics(const std::vector<double>& equity_values,
                                const std::vector<double>& trade_returns);

/// Check whether metrics meet activation thresholds.
bool passes_thresholds(const BacktestMetrics& m, double min_sharpe,
                       double max_dd, double min_wr);

}  // namespace quant_core
