#include "quant_core/metrics.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>

namespace quant_core {

BacktestMetrics compute_metrics(const std::vector<double>& equity_values,
                                const std::vector<double>& trade_returns) {
    BacktestMetrics m{0.0, 0.0, 0.0, 0.0, 0.0, 0.0};

    if (equity_values.size() < 2) {
        return m;
    }

    int n = static_cast<int>(equity_values.size());

    // Daily returns
    std::vector<double> daily_returns;
    daily_returns.reserve(n - 1);
    for (int i = 1; i < n; ++i) {
        if (equity_values[i - 1] != 0.0) {
            daily_returns.push_back(equity_values[i] / equity_values[i - 1] - 1.0);
        }
    }

    // CAGR
    double total_return = equity_values.back() / equity_values.front();
    double n_years = static_cast<double>(n) / 252.0;
    if (n_years > 0.0 && total_return > 0.0) {
        m.cagr = std::pow(total_return, 1.0 / n_years) - 1.0;
    }

    // Sharpe ratio (annualized, risk-free = 0)
    if (daily_returns.size() > 1) {
        double sum = std::accumulate(daily_returns.begin(), daily_returns.end(), 0.0);
        double mean = sum / static_cast<double>(daily_returns.size());
        double sq_sum = 0.0;
        for (double r : daily_returns) {
            sq_sum += (r - mean) * (r - mean);
        }
        double std_dev = std::sqrt(sq_sum / static_cast<double>(daily_returns.size() - 1));
        if (std_dev > 0.0) {
            m.sharpe = (mean / std_dev) * std::sqrt(252.0);
        }
    }

    // Max drawdown (positive fraction)
    double peak = equity_values[0];
    double max_dd = 0.0;
    for (int i = 0; i < n; ++i) {
        if (equity_values[i] > peak) {
            peak = equity_values[i];
        }
        if (peak > 0.0) {
            double dd = (peak - equity_values[i]) / peak;
            if (dd > max_dd) {
                max_dd = dd;
            }
        }
    }
    m.max_drawdown = max_dd;

    // Win rate
    if (!trade_returns.empty()) {
        int wins = 0;
        for (double r : trade_returns) {
            if (r > 0.0) ++wins;
        }
        m.win_rate = static_cast<double>(wins) / static_cast<double>(trade_returns.size());
    }

    // Turnover proxy: mean absolute daily return
    if (!daily_returns.empty()) {
        double abs_sum = 0.0;
        for (double r : daily_returns) {
            abs_sum += std::abs(r);
        }
        m.turnover = abs_sum / static_cast<double>(daily_returns.size());
    }

    // Average trade return
    if (!trade_returns.empty()) {
        double sum = std::accumulate(trade_returns.begin(), trade_returns.end(), 0.0);
        m.avg_trade_return = sum / static_cast<double>(trade_returns.size());
    }

    return m;
}

bool passes_thresholds(const BacktestMetrics& m, double min_sharpe,
                       double max_dd, double min_wr) {
    return m.sharpe >= min_sharpe && m.max_drawdown <= max_dd && m.win_rate >= min_wr;
}

}  // namespace quant_core
