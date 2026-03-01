#include <catch2/catch_test_macros.hpp>
#include <catch2/matchers/catch_matchers_floating_point.hpp>

#include "quant_core/cost_model.hpp"

using namespace quant_core;
using Catch::Matchers::WithinRel;

TEST_CASE("CostModel apply_costs BUY increases price", "[cost_model]") {
    CostModel cm{1.0, 5.0, 2.0};
    double price = 100.0;
    double fill = cm.apply_costs(price, 10.0, "BUY");
    REQUIRE(fill > price);
    // impact_bps = 5.0 + 2.0/2 = 6.0
    // fill = 100 * (1 + 6/10000) = 100.06
    REQUIRE_THAT(fill, WithinRel(100.06, 1e-9));
}

TEST_CASE("CostModel apply_costs SELL decreases price", "[cost_model]") {
    CostModel cm{1.0, 5.0, 2.0};
    double price = 100.0;
    double fill = cm.apply_costs(price, 10.0, "SELL");
    REQUIRE(fill < price);
    REQUIRE_THAT(fill, WithinRel(99.94, 1e-9));
}

TEST_CASE("CostModel trade_commission returns flat fee", "[cost_model]") {
    CostModel cm{2.50, 0.0, 0.0};
    REQUIRE_THAT(cm.trade_commission(), WithinRel(2.50, 1e-9));
}

TEST_CASE("CostModel total_cost_for_trade includes impact + commission", "[cost_model]") {
    CostModel cm{1.0, 5.0, 2.0};
    double total = cm.total_cost_for_trade(100.0, 10.0, "BUY");
    // price_impact = |100.06 - 100| * 10 = 0.6
    // total = 0.6 + 1.0 = 1.6
    REQUIRE_THAT(total, WithinRel(1.6, 1e-6));
}

TEST_CASE("CostModel zero costs", "[cost_model]") {
    CostModel cm{0.0, 0.0, 0.0};
    REQUIRE_THAT(cm.apply_costs(100.0, 10.0, "BUY"), WithinRel(100.0, 1e-9));
    REQUIRE_THAT(cm.apply_costs(100.0, 10.0, "SELL"), WithinRel(100.0, 1e-9));
    REQUIRE_THAT(cm.total_cost_for_trade(100.0, 10.0, "BUY"), WithinRel(0.0, 1e-9));
}
