#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "quant_core/paper_broker.hpp"

namespace py = pybind11;

void bind_paper_broker(py::module_& m) {
    py::class_<quant_core::PaperBroker>(m, "CppPaperBroker")
        .def(py::init<double, quant_core::CostModel>(),
             py::arg("initial_cash"), py::arg("cost_model"))
        .def("submit_order", &quant_core::PaperBroker::submit_order,
             py::arg("ticker"), py::arg("side"), py::arg("qty"), py::arg("price"))
        .def("get_positions", &quant_core::PaperBroker::get_positions)
        .def("get_cash", &quant_core::PaperBroker::get_cash)
        .def("get_portfolio_value", &quant_core::PaperBroker::get_portfolio_value,
             py::arg("prices"))
        .def("get_orders", &quant_core::PaperBroker::get_orders)
        .def("realized_pnl", &quant_core::PaperBroker::realized_pnl)
        .def("unrealized_pnl", &quant_core::PaperBroker::unrealized_pnl,
             py::arg("prices"))
        .def("gross_exposure", &quant_core::PaperBroker::gross_exposure,
             py::arg("prices"));
}
