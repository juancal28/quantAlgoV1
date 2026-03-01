#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "quant_core/order.hpp"
#include "quant_core/position.hpp"

namespace py = pybind11;

void bind_order_position(py::module_& m) {
    py::class_<quant_core::Order>(m, "CppOrder")
        .def(py::init<>())
        .def_readwrite("ticker", &quant_core::Order::ticker)
        .def_readwrite("side", &quant_core::Order::side)
        .def_readwrite("quantity", &quant_core::Order::quantity)
        .def_readwrite("price", &quant_core::Order::price)
        .def_readwrite("status", &quant_core::Order::status)
        .def("__repr__", [](const quant_core::Order& o) {
            return "<CppOrder " + o.ticker + " " + o.side + " qty=" +
                   std::to_string(o.quantity) + " price=" + std::to_string(o.price) +
                   " status=" + o.status + ">";
        });

    py::class_<quant_core::Position>(m, "CppPosition")
        .def(py::init<>())
        .def_readwrite("ticker", &quant_core::Position::ticker)
        .def_readwrite("quantity", &quant_core::Position::quantity)
        .def_readwrite("avg_entry_price", &quant_core::Position::avg_entry_price)
        .def("__repr__", [](const quant_core::Position& p) {
            return "<CppPosition " + p.ticker + " qty=" +
                   std::to_string(p.quantity) + " avg_entry=" +
                   std::to_string(p.avg_entry_price) + ">";
        });
}
