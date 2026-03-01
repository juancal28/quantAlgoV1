#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "quant_core/signal_reconciler.hpp"

namespace py = pybind11;

void bind_signal_reconciler(py::module_& m) {
    py::class_<quant_core::ReconcileResult>(m, "CppReconcileResult")
        .def_readonly("to_buy", &quant_core::ReconcileResult::to_buy)
        .def_readonly("to_sell", &quant_core::ReconcileResult::to_sell);

    m.def("cpp_reconcile_positions", &quant_core::reconcile_positions,
          py::arg("signals"), py::arg("current_positions"));

    m.def("cpp_execute_signals", &quant_core::execute_signals,
          py::arg("broker"), py::arg("signals"), py::arg("current_prices"),
          py::arg("max_positions"), py::arg("max_position_pct"),
          py::arg("circuit_breaker_tripped"),
          py::arg("max_gross_exposure"), py::arg("max_trades_per_hour"));
}
