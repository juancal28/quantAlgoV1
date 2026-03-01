#pragma once

#include <string>

namespace quant_core {

struct Position {
    std::string ticker;
    double quantity;
    double avg_entry_price;
};

}  // namespace quant_core
