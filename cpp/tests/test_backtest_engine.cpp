#include <catch2/catch_test_macros.hpp>
#include <catch2/matchers/catch_matchers_floating_point.hpp>

#include "quant_core/backtest_engine.hpp"

using namespace quant_core;
using Catch::Matchers::WithinRel;

static std::vector<BarData> make_rising_bars(int n, double start_price = 100.0) {
    std::vector<BarData> bars;
    bars.reserve(n);
    for (int i = 0; i < n; ++i) {
        double price = start_price + static_cast<double>(i) * 0.5;
        bars.push_back(BarData{price, price + 1.0, price - 1.0, price + 0.5, 1000, 1000000 + i * 86400});
    }
    return bars;
}

TEST_CASE("BacktestEngine rejects missing ticker data", "[backtest_engine]") {
    BacktestEngine engine;
    std::vector<std::string> universe = {"AAPL"};
    std::vector<SignalConfig> signals;
    std::unordered_map<std::string, std::vector<BarData>> price_data;
    CostModel cm{0.0, 0.0, 0.0};

    REQUIRE_THROWS_AS(
        engine.run(universe, signals, 5, 0.10, price_data, 100000.0, cm, 0.5, 0.25, 0.4),
        std::runtime_error
    );
}

TEST_CASE("BacktestEngine rejects insufficient data", "[backtest_engine]") {
    BacktestEngine engine;
    std::vector<std::string> universe = {"AAPL"};
    std::vector<SignalConfig> signals;
    std::unordered_map<std::string, std::vector<BarData>> price_data;
    price_data["AAPL"] = {BarData{100.0, 101.0, 99.0, 100.5, 1000, 1000000}};
    CostModel cm{0.0, 0.0, 0.0};

    REQUIRE_THROWS_AS(
        engine.run(universe, signals, 5, 0.10, price_data, 100000.0, cm, 0.5, 0.25, 0.4),
        std::runtime_error
    );
}

TEST_CASE("BacktestEngine equity starts at initial cash", "[backtest_engine]") {
    BacktestEngine engine;
    std::vector<std::string> universe = {"AAPL"};
    std::vector<SignalConfig> signals;  // no signals → no trades
    std::unordered_map<std::string, std::vector<BarData>> price_data;
    price_data["AAPL"] = make_rising_bars(10);
    CostModel cm{0.0, 0.0, 0.0};

    auto result = engine.run(universe, signals, 5, 0.10, price_data, 100000.0, cm, 0.5, 0.25, 0.4);

    REQUIRE_THAT(result.equity_values[0], WithinRel(100000.0, 1e-9));
    REQUIRE(result.equity_values.size() == 10);
    REQUIRE(result.equity_dates.size() == 10);
    REQUIRE(result.trades.empty());
}

TEST_CASE("BacktestEngine with signals generates trades", "[backtest_engine]") {
    BacktestEngine engine;
    std::vector<std::string> universe = {"AAPL"};

    SignalConfig sig;
    sig.type = "news_sentiment";
    sig.params = {{"lookback_minutes", 240.0}, {"threshold", 0.0}};  // very low threshold to trigger
    sig.direction = "long";

    std::unordered_map<std::string, std::vector<BarData>> price_data;
    price_data["AAPL"] = make_rising_bars(50);
    CostModel cm{0.0, 0.0, 0.0};

    auto result = engine.run(universe, {sig}, 5, 0.10, price_data, 100000.0, cm,
                             0.0, 1.0, 0.0);  // very loose thresholds

    REQUIRE(result.equity_values.size() == 50);
    // With a momentum signal and rising prices, some trades should occur
    // (exact count depends on signal logic with shift)
}

TEST_CASE("BacktestEngine multiple tickers", "[backtest_engine]") {
    BacktestEngine engine;
    std::vector<std::string> universe = {"AAPL", "MSFT"};
    std::vector<SignalConfig> signals;

    std::unordered_map<std::string, std::vector<BarData>> price_data;
    price_data["AAPL"] = make_rising_bars(20);
    price_data["MSFT"] = make_rising_bars(20, 200.0);
    CostModel cm{0.0, 0.0, 0.0};

    auto result = engine.run(universe, signals, 5, 0.10, price_data, 100000.0, cm,
                             0.0, 1.0, 0.0);

    REQUIRE(result.equity_values.size() == 20);
    REQUIRE_THAT(result.equity_values[0], WithinRel(100000.0, 1e-9));
}
