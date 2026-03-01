#include <pybind11/pybind11.h>

#include "quant_core/position_sizer.hpp"

namespace py = pybind11;

void bind_position_sizer(py::module_& m) {
    m.def("cpp_compute_order_quantity", &quant_core::compute_order_quantity,
          py::arg("price"), py::arg("portfolio_value"), py::arg("cash_available"),
          py::arg("num_target_positions"), py::arg("max_position_pct"));
}
