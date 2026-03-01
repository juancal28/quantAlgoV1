#include <pybind11/pybind11.h>

namespace py = pybind11;

// Forward declarations for binding functions
void bind_cost_model(py::module_& m);
void bind_order_position(py::module_& m);
void bind_paper_broker(py::module_& m);
void bind_risk(py::module_& m);
void bind_position_sizer(py::module_& m);
void bind_signal_reconciler(py::module_& m);
void bind_metrics(py::module_& m);
void bind_backtest(py::module_& m);

PYBIND11_MODULE(_quant_core, m) {
    m.doc() = "C++ core for quant trading system (execution, backtesting, risk)";

    bind_order_position(m);
    bind_cost_model(m);
    bind_paper_broker(m);
    bind_risk(m);
    bind_position_sizer(m);
    bind_signal_reconciler(m);
    bind_metrics(m);
    bind_backtest(m);
}
