#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "quant_core/metrics.hpp"

namespace py = pybind11;

void bind_metrics(py::module_& m) {
    py::class_<quant_core::BacktestMetrics>(m, "CppBacktestMetrics")
        .def(py::init<>())
        .def_readwrite("cagr", &quant_core::BacktestMetrics::cagr)
        .def_readwrite("sharpe", &quant_core::BacktestMetrics::sharpe)
        .def_readwrite("max_drawdown", &quant_core::BacktestMetrics::max_drawdown)
        .def_readwrite("win_rate", &quant_core::BacktestMetrics::win_rate)
        .def_readwrite("turnover", &quant_core::BacktestMetrics::turnover)
        .def_readwrite("avg_trade_return", &quant_core::BacktestMetrics::avg_trade_return);

    m.def("cpp_compute_metrics", &quant_core::compute_metrics,
          py::arg("equity_values"), py::arg("trade_returns"));

    m.def("cpp_passes_thresholds", &quant_core::passes_thresholds,
          py::arg("metrics"), py::arg("min_sharpe"),
          py::arg("max_dd"), py::arg("min_wr"));
}
