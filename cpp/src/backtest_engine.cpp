#include "quant_core/backtest_engine.hpp"
#include "quant_core/metrics.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <stdexcept>
#include <vector>

namespace quant_core {

std::vector<double> BacktestEngine::generate_signals(
    const std::vector<BarData>& bars,
    const std::vector<SignalConfig>& signals_cfg) {

    int n = static_cast<int>(bars.size());
    std::vector<double> combined(n, 0.0);

    for (const auto& sig : signals_cfg) {
        if (sig.type == "news_sentiment") {
            double lookback_minutes = 240.0;
            auto it = sig.params.find("lookback_minutes");
            if (it != sig.params.end()) lookback_minutes = it->second;

            double threshold = 0.5;
            it = sig.params.find("threshold");
            if (it != sig.params.end()) threshold = it->second;

            // Convert minutes to approximate bar count (1Day bars = 390 min)
            int lookback_bars = std::max(static_cast<int>(lookback_minutes / 390.0), 1);

            // Momentum proxy: rolling return over lookback window
            for (int i = 0; i < n; ++i) {
                // lookahead guard: shift(1) — use bar i-1's signal for bar i
                int src = i - 1;
                if (src < lookback_bars) continue;

                double prev_open = bars[src - lookback_bars].open;
                if (prev_open <= 0.0) continue;
                double rolling_ret = bars[src].open / prev_open - 1.0;

                if (sig.direction == "long") {
                    if (rolling_ret > threshold * 0.01) {
                        combined[i] += 1.0;
                    }
                } else {
                    if (rolling_ret < -threshold * 0.01) {
                        combined[i] += 1.0;
                    }
                }
            }
        } else if (sig.type == "volatility_filter") {
            double max_vix = 25.0;
            auto it = sig.params.find("max_vix");
            if (it != sig.params.end()) max_vix = it->second;

            double vol_pct = max_vix / 100.0;
            int window = 20;

            // 20-day rolling annualized vol from open prices
            // First compute daily returns
            std::vector<double> returns(n, 0.0);
            for (int i = 1; i < n; ++i) {
                if (bars[i - 1].open > 0.0) {
                    returns[i] = bars[i].open / bars[i - 1].open - 1.0;
                }
            }

            for (int i = 0; i < n; ++i) {
                // lookahead guard: shift(1) — compute vol for bar i-1
                int src = i - 1;
                if (src < window) continue;

                // Rolling std of returns[src-window+1 .. src]
                double sum = 0.0;
                for (int j = src - window + 1; j <= src; ++j) {
                    sum += returns[j];
                }
                double mean = sum / static_cast<double>(window);
                double sq_sum = 0.0;
                for (int j = src - window + 1; j <= src; ++j) {
                    sq_sum += (returns[j] - mean) * (returns[j] - mean);
                }
                // Use sample std (ddof=1) to match pandas default
                double std_dev = std::sqrt(sq_sum / static_cast<double>(window - 1));
                double annualized_vol = std_dev * std::sqrt(252.0);

                if (annualized_vol < vol_pct) {
                    combined[i] += 1.0;
                }
            }
        }
    }

    return combined;
}

BacktestResult BacktestEngine::run(
    const std::vector<std::string>& universe,
    const std::vector<SignalConfig>& signals_cfg,
    int max_positions,
    double max_pos_pct,
    const std::unordered_map<std::string, std::vector<BarData>>& price_data,
    double initial_cash,
    const CostModel& cost_model,
    double min_sharpe,
    double max_drawdown_thresh,
    double min_win_rate) {

    // Validate data
    for (const auto& ticker : universe) {
        auto it = price_data.find(ticker);
        if (it == price_data.end()) {
            throw std::runtime_error("No price data for ticker '" + ticker + "'");
        }
        if (it->second.size() < 2) {
            throw std::runtime_error("Insufficient data for ticker '" + ticker + "'");
        }
    }

    // Build combined sorted date index (epoch -> set of tickers that have data)
    std::set<int64_t> all_dates_set;
    // Build per-ticker timestamp->index map for O(1) lookup
    std::unordered_map<std::string, std::unordered_map<int64_t, int>> ticker_ts_idx;
    for (const auto& ticker : universe) {
        const auto& bars = price_data.at(ticker);
        auto& idx_map = ticker_ts_idx[ticker];
        for (int i = 0; i < static_cast<int>(bars.size()); ++i) {
            all_dates_set.insert(bars[i].timestamp_epoch);
            idx_map[bars[i].timestamp_epoch] = i;
        }
    }

    std::vector<int64_t> dates(all_dates_set.begin(), all_dates_set.end());
    std::sort(dates.begin(), dates.end());

    // Pre-compute signals for each ticker
    std::unordered_map<std::string, std::vector<double>> ticker_signals;
    for (const auto& ticker : universe) {
        ticker_signals[ticker] = generate_signals(price_data.at(ticker), signals_cfg);
    }

    // Simulation state
    double cash = initial_cash;
    std::unordered_map<std::string, double> positions;     // ticker -> quantity
    std::unordered_map<std::string, double> entry_prices;  // ticker -> entry price
    std::vector<Trade> trades;
    std::vector<double> equity_values;
    std::vector<int64_t> equity_dates;

    equity_values.reserve(dates.size());
    equity_dates.reserve(dates.size());

    for (int64_t bar_time : dates) {
        // Calculate current portfolio value
        double portfolio_value = cash;
        for (const auto& [t, qty] : positions) {
            auto& idx_map = ticker_ts_idx[t];
            auto idx_it = idx_map.find(bar_time);
            if (idx_it != idx_map.end()) {
                portfolio_value += qty * price_data.at(t)[idx_it->second].open;
            } else if (entry_prices.count(t)) {
                portfolio_value += qty * entry_prices[t];
            }
        }

        equity_values.push_back(portfolio_value);
        equity_dates.push_back(bar_time);

        // Generate desired positions from signals
        std::vector<std::string> desired_tickers;
        for (const auto& ticker : universe) {
            auto& idx_map = ticker_ts_idx[ticker];
            auto idx_it = idx_map.find(bar_time);
            if (idx_it == idx_map.end()) continue;

            int bar_idx = idx_it->second;
            const auto& sig = ticker_signals[ticker];
            if (bar_idx < static_cast<int>(sig.size()) && sig[bar_idx] > 0.0) {
                desired_tickers.push_back(ticker);
            }
        }

        if (static_cast<int>(desired_tickers.size()) > max_positions) {
            desired_tickers.resize(max_positions);
        }

        // Close positions no longer desired
        std::vector<std::string> to_close;
        for (const auto& [ticker, qty] : positions) {
            if (std::find(desired_tickers.begin(), desired_tickers.end(), ticker) == desired_tickers.end()) {
                to_close.push_back(ticker);
            }
        }

        for (const auto& ticker : to_close) {
            auto& idx_map = ticker_ts_idx[ticker];
            auto idx_it = idx_map.find(bar_time);
            if (idx_it == idx_map.end()) continue;

            double qty = positions[ticker];
            double raw_price = price_data.at(ticker)[idx_it->second].open;
            double fill_price = cost_model.apply_costs(raw_price, qty, "SELL");
            double proceeds = qty * fill_price;
            cash += proceeds;
            double commission = cost_model.trade_commission();
            cash -= commission;
            double trade_pnl = (fill_price - entry_prices[ticker]) * qty - commission;

            trades.push_back(Trade{ticker, "SELL", qty, fill_price, trade_pnl, bar_time});
            positions.erase(ticker);
            entry_prices.erase(ticker);
        }

        // Open new positions
        for (const auto& ticker : desired_tickers) {
            if (positions.count(ticker)) continue;

            auto& idx_map = ticker_ts_idx[ticker];
            auto idx_it = idx_map.find(bar_time);
            if (idx_it == idx_map.end()) continue;

            double raw_price = price_data.at(ticker)[idx_it->second].open;
            if (raw_price <= 0.0) continue;

            // Position sizing: equal weight, capped at max_position_pct
            double target_value = std::min(
                portfolio_value / std::max(static_cast<int>(desired_tickers.size()), 1),
                portfolio_value * max_pos_pct
            );
            target_value = std::min(target_value, cash);
            if (target_value <= 0.0) continue;

            double fill_price = cost_model.apply_costs(raw_price, 0, "BUY");
            double qty = target_value / fill_price;
            double cost = qty * fill_price + cost_model.trade_commission();
            if (cost > cash) {
                qty = (cash - cost_model.trade_commission()) / fill_price;
            }
            if (qty <= 0.0) continue;

            cash -= qty * fill_price + cost_model.trade_commission();
            positions[ticker] = qty;
            entry_prices[ticker] = fill_price;
            trades.push_back(Trade{ticker, "BUY", qty, fill_price, 0.0, bar_time});
        }
    }

    // Compute trade returns (from closed trades only)
    std::vector<double> trade_returns;
    for (const auto& t : trades) {
        if (t.side == "SELL" && t.price > 0.0 && t.quantity > 0.0 && t.pnl != 0.0) {
            double entry_value = t.price * t.quantity - t.pnl;
            if (entry_value > 0.0) {
                trade_returns.push_back(t.pnl / entry_value);
            }
        }
    }

    BacktestMetrics metrics = compute_metrics(equity_values, trade_returns);
    bool passed = passes_thresholds(metrics, min_sharpe, max_drawdown_thresh, min_win_rate);

    return BacktestResult{metrics, passed, equity_values, equity_dates, trades};
}

}  // namespace quant_core
