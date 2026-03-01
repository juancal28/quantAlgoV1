#include <catch2/catch_test_macros.hpp>
#include <catch2/matchers/catch_matchers_floating_point.hpp>

#include "quant_core/paper_broker.hpp"

using namespace quant_core;
using Catch::Matchers::WithinRel;

TEST_CASE("PaperBroker starts with initial cash", "[paper_broker]") {
    CostModel cm{0.0, 0.0, 0.0};
    PaperBroker broker(100000.0, cm);
    REQUIRE_THAT(broker.get_cash(), WithinRel(100000.0, 1e-9));
    REQUIRE(broker.get_positions().empty());
    REQUIRE(broker.get_orders().empty());
}

TEST_CASE("PaperBroker BUY creates position", "[paper_broker]") {
    CostModel cm{0.0, 0.0, 0.0};
    PaperBroker broker(100000.0, cm);
    Order order = broker.submit_order("AAPL", "BUY", 10.0, 150.0);
    REQUIRE(order.status == "filled");
    REQUIRE(order.ticker == "AAPL");

    auto positions = broker.get_positions();
    REQUIRE(positions.size() == 1);
    REQUIRE(positions[0].ticker == "AAPL");
    REQUIRE_THAT(positions[0].quantity, WithinRel(10.0, 1e-9));
    REQUIRE_THAT(broker.get_cash(), WithinRel(98500.0, 1e-9));
}

TEST_CASE("PaperBroker BUY rejected if insufficient cash", "[paper_broker]") {
    CostModel cm{0.0, 0.0, 0.0};
    PaperBroker broker(1000.0, cm);
    Order order = broker.submit_order("AAPL", "BUY", 100.0, 150.0);
    REQUIRE(order.status == "rejected");
    REQUIRE(broker.get_positions().empty());
    REQUIRE_THAT(broker.get_cash(), WithinRel(1000.0, 1e-9));
}

TEST_CASE("PaperBroker SELL computes realized PnL", "[paper_broker]") {
    CostModel cm{0.0, 0.0, 0.0};
    PaperBroker broker(100000.0, cm);
    broker.submit_order("AAPL", "BUY", 10.0, 100.0);
    Order sell = broker.submit_order("AAPL", "SELL", 10.0, 110.0);
    REQUIRE(sell.status == "filled");
    // PnL = (110 - 100) * 10 - 0 = 100
    REQUIRE_THAT(broker.realized_pnl(), WithinRel(100.0, 1e-9));
    REQUIRE(broker.get_positions().empty());
}

TEST_CASE("PaperBroker SELL rejected if no position", "[paper_broker]") {
    CostModel cm{0.0, 0.0, 0.0};
    PaperBroker broker(100000.0, cm);
    Order order = broker.submit_order("AAPL", "SELL", 10.0, 150.0);
    REQUIRE(order.status == "rejected");
}

TEST_CASE("PaperBroker unrealized_pnl", "[paper_broker]") {
    CostModel cm{0.0, 0.0, 0.0};
    PaperBroker broker(100000.0, cm);
    broker.submit_order("AAPL", "BUY", 10.0, 100.0);
    PriceMap prices{{"AAPL", 110.0}};
    REQUIRE_THAT(broker.unrealized_pnl(prices), WithinRel(100.0, 1e-9));
}

TEST_CASE("PaperBroker gross_exposure", "[paper_broker]") {
    CostModel cm{0.0, 0.0, 0.0};
    PaperBroker broker(100000.0, cm);
    broker.submit_order("AAPL", "BUY", 10.0, 100.0);
    PriceMap prices{{"AAPL", 110.0}};
    REQUIRE_THAT(broker.gross_exposure(prices), WithinRel(1100.0, 1e-9));
}

TEST_CASE("PaperBroker portfolio_value", "[paper_broker]") {
    CostModel cm{0.0, 0.0, 0.0};
    PaperBroker broker(100000.0, cm);
    broker.submit_order("AAPL", "BUY", 10.0, 100.0);
    PriceMap prices{{"AAPL", 110.0}};
    // cash = 99000, positions = 10 * 110 = 1100, total = 100100
    REQUIRE_THAT(broker.get_portfolio_value(prices), WithinRel(100100.0, 1e-9));
}

TEST_CASE("PaperBroker weighted average entry on multiple buys", "[paper_broker]") {
    CostModel cm{0.0, 0.0, 0.0};
    PaperBroker broker(100000.0, cm);
    broker.submit_order("AAPL", "BUY", 10.0, 100.0);
    broker.submit_order("AAPL", "BUY", 10.0, 120.0);
    auto positions = broker.get_positions();
    REQUIRE(positions.size() == 1);
    REQUIRE_THAT(positions[0].quantity, WithinRel(20.0, 1e-9));
    // avg = (100*10 + 120*10) / 20 = 110
    REQUIRE_THAT(positions[0].avg_entry_price, WithinRel(110.0, 1e-9));
}
