#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "quant_core/backtest_engine.hpp"

namespace py = pybind11;

void bind_backtest(py::module_& m) {
    py::class_<quant_core::BarData>(m, "CppBarData")
        .def(py::init([](double open, double high, double low, double close,
                         int64_t volume, int64_t timestamp_epoch) {
            return quant_core::BarData{open, high, low, close, volume, timestamp_epoch};
        }), py::arg("open"), py::arg("high"), py::arg("low"), py::arg("close"),
            py::arg("volume"), py::arg("timestamp_epoch"))
        .def_readwrite("open", &quant_core::BarData::open)
        .def_readwrite("high", &quant_core::BarData::high)
        .def_readwrite("low", &quant_core::BarData::low)
        .def_readwrite("close", &quant_core::BarData::close)
        .def_readwrite("volume", &quant_core::BarData::volume)
        .def_readwrite("timestamp_epoch", &quant_core::BarData::timestamp_epoch);

    py::class_<quant_core::Trade>(m, "CppTrade")
        .def_readonly("ticker", &quant_core::Trade::ticker)
        .def_readonly("side", &quant_core::Trade::side)
        .def_readonly("quantity", &quant_core::Trade::quantity)
        .def_readonly("price", &quant_core::Trade::price)
        .def_readonly("pnl", &quant_core::Trade::pnl)
        .def_readonly("bar_time_epoch", &quant_core::Trade::bar_time_epoch);

    py::class_<quant_core::SignalConfig>(m, "CppSignalConfig")
        .def(py::init([](const std::string& type,
                         const std::unordered_map<std::string, double>& params,
                         const std::string& direction) {
            return quant_core::SignalConfig{type, params, direction};
        }), py::arg("type"), py::arg("params") = std::unordered_map<std::string, double>{},
            py::arg("direction") = "long")
        .def_readwrite("type", &quant_core::SignalConfig::type)
        .def_readwrite("params", &quant_core::SignalConfig::params)
        .def_readwrite("direction", &quant_core::SignalConfig::direction);

    py::class_<quant_core::BacktestResult>(m, "CppBacktestResult")
        .def_readonly("metrics", &quant_core::BacktestResult::metrics)
        .def_readonly("passed", &quant_core::BacktestResult::passed)
        .def_readonly("equity_values", &quant_core::BacktestResult::equity_values)
        .def_readonly("equity_dates", &quant_core::BacktestResult::equity_dates)
        .def_readonly("trades", &quant_core::BacktestResult::trades);

    py::class_<quant_core::BacktestEngine>(m, "CppBacktestEngine")
        .def(py::init<>())
        .def("run", &quant_core::BacktestEngine::run,
             py::arg("universe"), py::arg("signals_cfg"),
             py::arg("max_positions"), py::arg("max_pos_pct"),
             py::arg("price_data"), py::arg("initial_cash"),
             py::arg("cost_model"), py::arg("min_sharpe"),
             py::arg("max_drawdown"), py::arg("min_win_rate"));
}
