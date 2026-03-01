#include <pybind11/pybind11.h>

#include "quant_core/risk_checks.hpp"

namespace py = pybind11;

void bind_risk(py::module_& m) {
    py::class_<quant_core::CircuitBreakerResult>(m, "CppCircuitBreakerResult")
        .def_readonly("tripped", &quant_core::CircuitBreakerResult::tripped)
        .def_readonly("updated_peak_pnl", &quant_core::CircuitBreakerResult::updated_peak_pnl)
        .def_readonly("total_pnl", &quant_core::CircuitBreakerResult::total_pnl)
        .def_readonly("loss_pct", &quant_core::CircuitBreakerResult::loss_pct);

    m.def("cpp_check_circuit_breaker", &quant_core::check_circuit_breaker,
          py::arg("realized_pnl"), py::arg("unrealized_pnl"),
          py::arg("peak_pnl"), py::arg("initial_cash"),
          py::arg("max_daily_loss_pct"));

    m.def("cpp_check_exposure_limit", &quant_core::check_exposure_limit,
          py::arg("gross_exposure"), py::arg("portfolio_value"),
          py::arg("max_gross_exposure"));

    m.def("cpp_check_trade_rate_limit", &quant_core::check_trade_rate_limit,
          py::arg("recent_order_count"), py::arg("max_trades_per_hour"));
}
