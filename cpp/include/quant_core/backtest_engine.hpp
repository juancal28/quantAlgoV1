#pragma once

#include "quant_core/cost_model.hpp"
#include "quant_core/metrics.hpp"

#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace quant_core {

struct BarData {
    double open;
    double high;
    double low;
    double close;
    int64_t volume;
    int64_t timestamp_epoch;  // seconds since epoch
};

struct Trade {
    std::string ticker;
    std::string side;
    double quantity;
    double price;
    double pnl;
    int64_t bar_time_epoch;
};

struct BacktestResult {
    BacktestMetrics metrics;
    bool passed;
    std::vector<double> equity_values;
    std::vector<int64_t> equity_dates;
    std::vector<Trade> trades;
};

struct SignalConfig {
    std::string type;                                  // "news_sentiment" or "volatility_filter"
    std::unordered_map<std::string, double> params;    // lookback_minutes, threshold, max_vix, etc.
    std::string direction;                             // "long" or "short"
};

class BacktestEngine {
public:
    BacktestResult run(
        const std::vector<std::string>& universe,
        const std::vector<SignalConfig>& signals_cfg,
        int max_positions,
        double max_pos_pct,
        const std::unordered_map<std::string, std::vector<BarData>>& price_data,
        double initial_cash,
        const CostModel& cost_model,
        double min_sharpe,
        double max_drawdown,
        double min_win_rate
    );

private:
    /// Generate signal values for a ticker's bars.
    std::vector<double> generate_signals(
        const std::vector<BarData>& bars,
        const std::vector<SignalConfig>& signals_cfg
    );
};

}  // namespace quant_core
