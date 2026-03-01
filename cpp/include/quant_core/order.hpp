#pragma once

#include <string>

namespace quant_core {

struct Order {
    std::string ticker;
    std::string side;     // "BUY" or "SELL"
    double quantity;
    double price;
    std::string status;   // "filled" or "rejected"
};

}  // namespace quant_core
