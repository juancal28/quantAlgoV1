#include <catch2/catch_test_macros.hpp>
#include <catch2/matchers/catch_matchers_floating_point.hpp>

#include "quant_core/metrics.hpp"

using namespace quant_core;
using Catch::Matchers::WithinRel;

TEST_CASE("compute_metrics empty equity returns zeros", "[metrics]") {
    auto m = compute_metrics({}, {});
    REQUIRE(m.cagr == 0.0);
    REQUIRE(m.sharpe == 0.0);
    REQUIRE(m.max_drawdown == 0.0);
    REQUIRE(m.win_rate == 0.0);
}

TEST_CASE("compute_metrics single value returns zeros", "[metrics]") {
    auto m = compute_metrics({100000.0}, {});
    REQUIRE(m.cagr == 0.0);
    REQUIRE(m.sharpe == 0.0);
}

TEST_CASE("compute_metrics flat equity", "[metrics]") {
    std::vector<double> equity(100, 100000.0);
    auto m = compute_metrics(equity, {});
    REQUIRE_THAT(m.cagr, WithinRel(0.0, 1e-6));
    REQUIRE(m.max_drawdown == 0.0);
}

TEST_CASE("compute_metrics positive return", "[metrics]") {
    // 252 bars, steady growth
    std::vector<double> equity;
    equity.reserve(252);
    for (int i = 0; i < 252; ++i) {
        equity.push_back(100000.0 * (1.0 + 0.10 * i / 252.0));
    }
    auto m = compute_metrics(equity, {0.05, -0.02, 0.03});
    REQUIRE(m.cagr > 0.0);
    REQUIRE(m.sharpe > 0.0);
    // win_rate: 2 out of 3 positive
    REQUIRE_THAT(m.win_rate, WithinRel(2.0 / 3.0, 1e-9));
    REQUIRE_THAT(m.avg_trade_return, WithinRel(0.02, 1e-9));
}

TEST_CASE("compute_metrics drawdown", "[metrics]") {
    std::vector<double> equity = {100.0, 110.0, 100.0, 90.0, 95.0};
    auto m = compute_metrics(equity, {});
    // Peak is 110, worst is 90 => drawdown = 20/110 ≈ 0.1818
    REQUIRE(m.max_drawdown > 0.18);
    REQUIRE(m.max_drawdown < 0.19);
}

TEST_CASE("passes_thresholds works", "[metrics]") {
    BacktestMetrics good{0.1, 1.0, 0.15, 0.5, 0.01, 0.005};
    REQUIRE(passes_thresholds(good, 0.5, 0.25, 0.4));

    BacktestMetrics bad_sharpe{0.1, 0.3, 0.15, 0.5, 0.01, 0.005};
    REQUIRE_FALSE(passes_thresholds(bad_sharpe, 0.5, 0.25, 0.4));

    BacktestMetrics bad_dd{0.1, 1.0, 0.30, 0.5, 0.01, 0.005};
    REQUIRE_FALSE(passes_thresholds(bad_dd, 0.5, 0.25, 0.4));

    BacktestMetrics bad_wr{0.1, 1.0, 0.15, 0.3, 0.01, 0.005};
    REQUIRE_FALSE(passes_thresholds(bad_wr, 0.5, 0.25, 0.4));
}
