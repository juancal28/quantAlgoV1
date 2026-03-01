#include <pybind11/pybind11.h>

#include "quant_core/cost_model.hpp"

namespace py = pybind11;

void bind_cost_model(py::module_& m) {
    py::class_<quant_core::CostModel>(m, "CppCostModel")
        .def(py::init([](double commission, double slippage_bps, double spread_bps) {
            return quant_core::CostModel{commission, slippage_bps, spread_bps};
        }), py::arg("commission_per_trade"), py::arg("slippage_bps"), py::arg("spread_bps"))
        .def_readwrite("commission_per_trade", &quant_core::CostModel::commission_per_trade)
        .def_readwrite("slippage_bps", &quant_core::CostModel::slippage_bps)
        .def_readwrite("spread_bps", &quant_core::CostModel::spread_bps)
        .def("apply_costs", &quant_core::CostModel::apply_costs,
             py::arg("price"), py::arg("quantity"), py::arg("side"))
        .def("trade_commission", &quant_core::CostModel::trade_commission)
        .def("total_cost_for_trade", &quant_core::CostModel::total_cost_for_trade,
             py::arg("price"), py::arg("quantity"), py::arg("side"));
}
